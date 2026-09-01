# app/routers/commands.py
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import ValidationError

from databasev5 import get_db
from modelsv5 import User, dev_table, hub_table, pending_commands
from schemasv5 import ACCommand, ATSCommand, CommandStatusResponse
from auth import get_current_user
from app.dependencies import verify_hub_identity
from app.core.rate_limit import limiter

router = APIRouter(tags=["commands"])


@router.post("/api/devices/{dev_id}/command")
@limiter.limit("30/minute")
def send_device_command(
    request: Request,
    dev_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_reset = body.get("reset") is not None
    if is_reset:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reset action requires admin role",
            )
    else:
        if current_user.role not in ["admin", "operator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action requires admin or operator role",
            )

    device = db.query(dev_table).filter(or_(dev_table.dev_id == dev_id, dev_table.dev_name == dev_id)).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        if device.dev_type in ("AC", "ACC") or "target" in body or "action" in body:
            validated_command = ACCommand.model_validate(body)
        else:
            validated_command = ATSCommand.model_validate(body, context={"db": db, "dev_id": device.dev_id})
    except ValidationError as err:
        from fastapi.exceptions import RequestValidationError
        raise RequestValidationError(err.errors())

    new_cmd = pending_commands(
        command_id=str(uuid.uuid4()),
        dev_id=device.dev_id,
        hub_id=device.hub_id,
        payload=validated_command.model_dump(mode="json"),
        status="pending",
    )
    db.add(new_cmd)
    db.commit()
    return {"status": "queued", "command_id": new_cmd.command_id}


@router.get("/api/hub/commands")
@limiter.limit("30/minute")
def get_pending_commands(
    request: Request,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    cmds = db.query(pending_commands).filter(
        pending_commands.hub_id == hub.hub_id,
        pending_commands.status == "pending",
    ).all()

    return [
        {
            "command_id": cmd.command_id,
            "dev_id": cmd.dev_id,
            "payload": cmd.payload,
            "status": cmd.status,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
        }
        for cmd in cmds
    ]


@router.post("/api/hub/commands/{command_id}/delivered")
@limiter.limit("30/minute")
def mark_command_delivered(
    request: Request,
    command_id: str,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    cmd = db.get(pending_commands, command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    if cmd.hub_id != hub.hub_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this command")

    cmd.status = "delivered"
    cmd.delivered_at = datetime.now(UTC)
    db.commit()
    return {"status": "marked_delivered", "command_id": command_id}


@router.get("/api/commands/{command_id}", response_model=CommandStatusResponse)
@limiter.limit("60/minute")
def get_command_status(
    request: Request,
    command_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmd = db.get(pending_commands, command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    device = db.get(dev_table, cmd.dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if cmd.hub_id:
        hub = db.get(hub_table, cmd.hub_id)
        if not hub:
            raise HTTPException(status_code=404, detail="Hub not found")

    return cmd
