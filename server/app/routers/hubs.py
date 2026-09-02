# app/routers/hubs.py
import os
import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import dev_table, hub_table
from schemasv5 import HubRegisterPayload, HubResponse, HubDeviceSummary, HubPairRequest, GatewayRoomAssign
from modelsv5 import User, rooms
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.dependencies import hub_auth_cache

router = APIRouter(tags=["hubs"])

HUB_ONLINE_WINDOW_SECONDS = 25


@router.post("/api/admin/hubs")
@limiter.limit("10/minute")
def register_new_hub(
    request: Request,
    payload: HubRegisterPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    exist = db.get(hub_table, payload.HUB_ID)
    if exist:
        raise HTTPException(status_code=400, detail="HUB_ID sudah terdaftar!")

    new_hub = hub_table(
        hub_id=payload.HUB_ID,
        hub_name=payload.HUB_NAME,
        hub_key=payload.HUB_KEY,
        is_active=True,
    )
    db.add(new_hub)
    db.commit()
    hub_auth_cache.invalidate(payload.HUB_ID)
    return {"status": "hub_registered", "hub_id": payload.HUB_ID}


@router.get("/api/hubs", response_model=list[HubResponse])
@limiter.limit("60/minute")
def list_hubs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=HUB_ONLINE_WINDOW_SECONDS)

    # Query 1: Hubs with SQL-aggregated device count
    hub_stmt = (
        select(
            hub_table,
            func.count(dev_table.dev_id).label("device_count"),
        )
        .outerjoin(dev_table, dev_table.hub_id == hub_table.hub_id)
        .group_by(hub_table.hub_id)
        .order_by(hub_table.created_at.asc())
    )
    hub_rows = db.execute(hub_stmt).all()

    # Query 2: Lightweight projection query for device summaries
    dev_stmt = (
        select(
            dev_table.hub_id,
            dev_table.dev_id,
            dev_table.dev_name,
            dev_table.dev_type,
            dev_table.last_seen,
        )
        .where(dev_table.hub_id.isnot(None))
    )
    devices_by_hub: dict[str, list[HubDeviceSummary]] = defaultdict(list)
    for row in db.execute(dev_stmt).mappings():
        devices_by_hub[row["hub_id"]].append(
            HubDeviceSummary(
                dev_id=row["dev_id"],
                dev_name=row["dev_name"],
                dev_type=row["dev_type"],
                last_seen=row["last_seen"],
            )
        )

    results = []
    for h, dev_count in hub_rows:
        h_seen = h.last_seen if (h.last_seen and h.last_seen.tzinfo is not None) else (h.last_seen.replace(tzinfo=UTC) if h.last_seen else None)
        hub_status = "online" if (h_seen and h_seen >= cutoff) else "offline"

        results.append(
            HubResponse(
                hub_id=h.hub_id,
                hub_name=h.hub_name,
                room=h.room,
                status=hub_status,
                last_seen=h.last_seen,
                device_count=dev_count,
                devices=devices_by_hub.get(h.hub_id, []),
            )
        )
    return results


@router.post("/api/hubs/pair")
@limiter.limit("10/minute")
def pair_hub(
    request: Request,
    payload: HubPairRequest,
    x_hub_key: str = Header(..., alias="X-Hub-Key"),
    db: Session = Depends(get_db),
):
    existing = db.get(hub_table, payload.hub_id)
    now_utc = datetime.now(UTC)

    if existing and existing.is_active:
        stored_key = existing.hub_key or ""
        if not secrets.compare_digest(stored_key, x_hub_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: API Key Hub tidak cocok!",
            )
        existing.last_seen = now_utc
        existing.status = "online"
        db.commit()
        hub_auth_cache.invalidate(payload.hub_id)
        return {"status": "paired", "hub_id": existing.hub_id}

    bootstrap_key = os.getenv("HUB_BOOTSTRAP_KEY", "")
    if not bootstrap_key or not secrets.compare_digest(bootstrap_key, x_hub_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: Hub tidak terdaftar atau API Key bootstrap tidak cocok!",
        )

    if not existing:
        clean_name = payload.hub_name.strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="HUB_NAME tidak boleh kosong!",
            )
        new_hub = hub_table(
            hub_id=payload.hub_id,
            hub_name=clean_name,
            hub_key=x_hub_key,
            is_active=False,
            status="offline",
            created_at=now_utc,
        )
        db.add(new_hub)
        db.commit()

    hub_auth_cache.invalidate(payload.hub_id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "pending_approval", "hub_id": payload.hub_id})


@router.post("/api/hubs/{hub_id}/approve")
@limiter.limit("30/minute")
def approve_hub(
    request: Request,
    hub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub tidak ditemukan")

    hub.is_active = True
    db.commit()
    hub_auth_cache.invalidate(hub_id)
    return {"status": "approved", "hub_id": hub_id}


@router.post("/api/hubs/{hub_id}/revoke")
@limiter.limit("30/minute")
def revoke_hub(
    request: Request,
    hub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub tidak ditemukan")

    hub.is_active = False
    hub.status = "offline"
    db.commit()
    hub_auth_cache.invalidate(hub_id)
    return {"status": "revoked", "hub_id": hub_id}


@router.post("/api/gateways/{hub_id}/room")
@limiter.limit("30/minute")
def assign_gateway_room(
    request: Request,
    hub_id: str,
    payload: GatewayRoomAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway '{hub_id}' not found",
        )

    room = db.get(rooms, payload.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{payload.room_id}' not found",
        )

    room.hub_id = hub.hub_id
    hub.room = room.name
    db.commit()
    return {"status": "assigned", "hub_id": hub_id, "room_id": payload.room_id}


@router.delete("/api/hubs/{hub_id}")
@limiter.limit("30/minute")
def delete_hub(
    request: Request,
    hub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Hard-delete a hub. Refuses (409) while devices are still paired to it;
    room assignments referencing the hub are cleared (rooms are never deleted)."""
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub tidak ditemukan")

    device_count = db.query(dev_table).filter(dev_table.hub_id == hub_id).count()
    if device_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Hub still has {device_count} paired device(s); unpair or move them first",
        )

    db.query(rooms).filter(rooms.hub_id == hub_id).update({"hub_id": None})
    db.delete(hub)
    db.commit()
    hub_auth_cache.invalidate(hub_id)
    return {"status": "deleted", "hub_id": hub_id}