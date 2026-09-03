# app/routers/schedules.py — CRUD for flexible ATS scheduling
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import User, dev_table, hub_table, schedules
from schemasv5 import ACCommand, ATSCommand
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.services.scheduler import (
    CANONICAL_TZ,
    fire_schedule,
    get_next_runs,
    human_cron,
    remove_job,
    sync_job,
    _validate_cron_expr,
)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


# Schemas
class ScheduleCreate(BaseModel):
    dev_id: str = Field(..., min_length=1, max_length=100)
    hub_id: Optional[str] = Field(None, max_length=100)
    cron_expr: str = Field(..., max_length=64)
    payload: dict[str, Any]
    tz: str = Field(default=CANONICAL_TZ, max_length=32)
    enabled: bool = Field(default=True)

    @field_validator("cron_expr")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        _validate_cron_expr(v, CANONICAL_TZ)
        return v.strip()

    @field_validator("tz")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        if not v:
            return CANONICAL_TZ
        # Validate via zoneinfo
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone '{v}'")
        return v


class ScheduleUpdate(BaseModel):
    dev_id: Optional[str] = Field(None, max_length=100)
    hub_id: Optional[str] = Field(None, max_length=100)
    cron_expr: Optional[str] = Field(None, max_length=64)
    payload: Optional[dict[str, Any]] = None
    tz: Optional[str] = Field(None, max_length=32)
    enabled: Optional[bool] = None

    @field_validator("cron_expr")
    @classmethod
    def validate_cron_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        _validate_cron_expr(v, CANONICAL_TZ)
        return v.strip()

    @field_validator("tz")
    @classmethod
    def validate_tz_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone '{v}'")
        return v


class ScheduleResponse(BaseModel):
    id: str
    dev_id: str
    hub_id: Optional[str] = None
    cron_expr: str
    payload: dict[str, Any]
    tz: str
    enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime] = None
    next_run: Optional[datetime] = None
    next_runs: list[datetime] = Field(default_factory=list)
    human: Optional[str] = None

    model_config = {"from_attributes": True}


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate payload against ATSCommand or ACCommand whitelist. Raises 422 if invalid."""
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=422, detail="payload must be a non-empty object")
    # Try ATSCommand
    # Note: ATSCommand.check_genset_mode requires db context for bare start_genset:on
    # For schedules, bundled payload {mode:manual,start_genset:on} is canonical and should pass without DB.
    # So validate without DB context first; if that fails due to mode guard, accept bundled.
    try:
        # Use mode bypass path: if payload has both mode manual + start_genset on, ATSCommand will pass without DB
        obj = ATSCommand.model_validate(payload)
        return obj.model_dump(mode="json", exclude_none=True)
    except Exception:
        pass
    try:
        obj = ACCommand.model_validate(payload)
        return obj.model_dump(mode="json", exclude_none=True)
    except Exception as e:
        # Provide detailed error
        # Re-attempt to give better message: if ATSCommand failed, report ATS error
        try:
            ATSCommand.model_validate(payload)
        except Exception as ats_e:
            raise HTTPException(status_code=422, detail=f"Invalid payload: {ats_e}")
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")
    # unreachable


def _is_reset_payload(payload: dict[str, Any]) -> bool:
    return payload.get("reset") is not None


def _to_response(obj: schedules) -> dict:
    nxt_runs = get_next_runs(obj.cron_expr, obj.tz or CANONICAL_TZ, 3)
    nxt = nxt_runs[0] if nxt_runs else obj.next_run_at
    human = human_cron(obj.cron_expr)
    return {
        "id": obj.id,
        "dev_id": obj.dev_id,
        "hub_id": obj.hub_id,
        "cron_expr": obj.cron_expr,
        "payload": obj.payload,
        "tz": obj.tz,
        "enabled": obj.enabled,
        "created_by": obj.created_by,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "next_run_at": nxt,
        "next_run": nxt,
        "next_runs": nxt_runs,
        "human": human,
    }


# Endpoints

@router.get("/preview")
@limiter.limit("30/minute")
def preview_cron(
    request: Request,
    cron_expr: str = Query(..., max_length=64),
    tz: str = Query(default=CANONICAL_TZ, max_length=32),
    current_user: User = Depends(get_current_user),
):
    try:
        _validate_cron_expr(cron_expr, tz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    nxt = get_next_runs(cron_expr, tz, 3)
    human = human_cron(cron_expr)
    return {"cron_expr": cron_expr, "tz": tz, "human": human, "next_runs": [n.isoformat() for n in nxt], "next_run": nxt[0].isoformat() if nxt else None}


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_schedule(
    request: Request,
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    # Validate payload whitelist
    validated_payload = _validate_payload(body.payload)

    # Validate tz via body (already done) but need to re-validate cron with actual tz
    try:
        _validate_cron_expr(body.cron_expr, body.tz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Validate device exists
    device = db.get(dev_table, body.dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Validate hub if provided
    hub_id = body.hub_id or device.hub_id
    if hub_id:
        hub = db.get(hub_table, hub_id)
        if not hub:
            raise HTTPException(status_code=404, detail="Hub not found")
    else:
        hub_id = device.hub_id

    sched_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    nxt = get_next_runs(body.cron_expr, body.tz, 1)
    next_run_at = nxt[0] if nxt else None

    row = schedules(
        id=sched_id,
        dev_id=body.dev_id,
        hub_id=hub_id,
        cron_expr=body.cron_expr.strip(),
        payload=validated_payload,
        tz=body.tz,
        enabled=body.enabled,
        created_by=current_user.username,
        created_at=now,
        updated_at=now,
        next_run_at=next_run_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Sync scheduler
    try:
        sync_job(row.id, row.cron_expr, row.tz, row.enabled)
    except Exception:
        pass

    return _to_response(row)


@router.get("")
@limiter.limit("60/minute")
def list_schedules(
    request: Request,
    hub_id: Optional[str] = Query(None),
    dev_id: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(schedules)
    if hub_id is not None:
        q = q.filter(schedules.hub_id == hub_id)
    if dev_id is not None:
        q = q.filter(schedules.dev_id == dev_id)
    if enabled is not None:
        q = q.filter(schedules.enabled == enabled)
    rows = q.order_by(schedules.created_at.desc()).all()
    return [_to_response(r) for r in rows]


@router.get("/{schedule_id}")
@limiter.limit("60/minute")
def get_schedule(
    request: Request,
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.get(schedules, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_response(obj)


@router.patch("/{schedule_id}")
@limiter.limit("30/minute")
def update_schedule(
    request: Request,
    schedule_id: str,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    obj = db.get(schedules, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updates = body.model_dump(exclude_unset=True)
    # Validate payload if present
    if "payload" in updates and updates["payload"] is not None:
        validated = _validate_payload(updates["payload"])
        obj.payload = validated
    if "cron_expr" in updates and updates["cron_expr"] is not None:
        # validate with tz (new or existing)
        tz = updates.get("tz", obj.tz)
        try:
            _validate_cron_expr(updates["cron_expr"], tz)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        obj.cron_expr = updates["cron_expr"].strip()
    if "tz" in updates and updates["tz"] is not None:
        obj.tz = updates["tz"]
        # revalidate cron with new tz
        try:
            _validate_cron_expr(obj.cron_expr, obj.tz)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    if "dev_id" in updates and updates["dev_id"] is not None:
        dev = db.get(dev_table, updates["dev_id"])
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")
        obj.dev_id = updates["dev_id"]
    if "hub_id" in updates:
        # hub_id can be None to clear? allow
        if updates["hub_id"] is not None:
            hub = db.get(hub_table, updates["hub_id"])
            if not hub:
                raise HTTPException(status_code=404, detail="Hub not found")
        obj.hub_id = updates["hub_id"]
    if "enabled" in updates and updates["enabled"] is not None:
        obj.enabled = updates["enabled"]

    obj.updated_at = datetime.now(UTC)
    # update next_run_at
    nxt = get_next_runs(obj.cron_expr, obj.tz, 1)
    obj.next_run_at = nxt[0] if nxt else None

    db.commit()
    db.refresh(obj)

    # Sync scheduler
    try:
        sync_job(obj.id, obj.cron_expr, obj.tz, obj.enabled)
    except Exception:
        pass

    return _to_response(obj)


@router.delete("/{schedule_id}")
@limiter.limit("30/minute")
def delete_schedule(
    request: Request,
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    obj = db.get(schedules, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(obj)
    db.commit()
    try:
        remove_job(schedule_id)
    except Exception:
        pass
    return {"status": "deleted", "id": schedule_id}


@router.post("/{schedule_id}/run-now")
@limiter.limit("30/minute")
def run_schedule_now(
    request: Request,
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    obj = db.get(schedules, schedule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    # Fire immediately (insert pending_commands)
    try:
        fire_schedule(schedule_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fire schedule: {e}")
    return {"status": "fired", "id": schedule_id}
