# app/routers/alerts.py
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import User, dev_table, event_log, rooms
from schemasv5 import AlertListResponse, AlertResponse
from auth import get_current_user, get_user_cluster_ids
from app.core.rate_limit import limiter

router = APIRouter(tags=["alerts"])


def parse_datetime_param(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    val_str = str(val).strip()
    try:
        if val_str.endswith("Z") or val_str.endswith("z"):
            val_str = val_str[:-1] + "+00:00"
        elif " " in val_str and ("+" not in val_str and "-" not in val_str[10:]):
            parts = val_str.rsplit(" ", 1)
            if len(parts) == 2 and (":" in parts[1] or len(parts[1]) in (2, 4, 5)):
                val_str = f"{parts[0]}+{parts[1]}"
        return datetime.fromisoformat(val_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime format: '{val}'. Expected ISO format (e.g. YYYY-MM-DDTHH:MM:SSZ).",
        )


@router.get("/api/alerts", response_model=AlertListResponse)
@limiter.limit("60/minute")
def get_alerts(
    request: Request,
    rooms_param: Optional[list[str]] = Query(None, alias="rooms"),
    room_param: Optional[str] = Query(None, alias="room"),
    devices_param: Optional[list[str]] = Query(None, alias="devices"),
    device_param: Optional[str] = Query(None, alias="device"),
    cluster_filter: Optional[str] = Query(None, alias="cluster_id"),
    severity: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(
            event_log,
            dev_table.dev_name.label("device_name"),
            rooms.name.label("room_name"),
        )
        .outerjoin(dev_table, event_log.dev_id == dev_table.dev_id)
        .outerjoin(rooms, event_log.room_id == rooms.id)
    )

    # Scoping by cluster
    if current_user.role != "root":
        user_clusters = get_user_cluster_ids(current_user, db)
        if user_clusters:
            if cluster_filter:
                if cluster_filter not in user_clusters:
                    return AlertListResponse(total=0, alerts=[])
                query = query.filter(or_(dev_table.cluster_id == cluster_filter, rooms.cluster_id == cluster_filter))
            else:
                query = query.filter(or_(dev_table.cluster_id.in_(user_clusters), rooms.cluster_id.in_(user_clusters)))
        else:
            if cluster_filter:
                query = query.filter(or_(dev_table.cluster_id == cluster_filter, rooms.cluster_id == cluster_filter))
    else:
        if cluster_filter:
            query = query.filter(or_(dev_table.cluster_id == cluster_filter, rooms.cluster_id == cluster_filter))

    parsed_rooms = []
    if rooms_param:
        for r in rooms_param:
            parsed_rooms.extend([x.strip() for x in r.split(",") if x.strip()])
    if room_param:
        parsed_rooms.extend([x.strip() for x in room_param.split(",") if x.strip()])
    if parsed_rooms:
        query = query.filter(event_log.room_id.in_(parsed_rooms))

    parsed_devices = []
    if devices_param:
        for d in devices_param:
            parsed_devices.extend([x.strip() for x in d.split(",") if x.strip()])
    if device_param:
        parsed_devices.extend([x.strip() for x in device_param.split(",") if x.strip()])
    if parsed_devices:
        query = query.filter(event_log.dev_id.in_(parsed_devices))

    if severity:
        sev = severity.strip().lower()
        if sev in ("warning", "critical"):
            query = query.filter(event_log.severity == sev)
        elif sev == "all":
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid severity filter. Use 'warning', 'critical', or 'all'.",
            )

    if status_filter:
        st = status_filter.strip().lower()
        if st == "open":
            query = query.filter(event_log.resolved_at.is_(None))
        elif st == "resolved":
            query = query.filter(event_log.resolved_at.isnot(None))
        elif st == "all":
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status filter. Use 'open', 'resolved', or 'all'.",
            )

    parsed_start = parse_datetime_param(start_time)
    parsed_end = parse_datetime_param(end_time)
    if parsed_start is not None:
        query = query.filter(event_log.timestamp >= parsed_start)
    if parsed_end is not None:
        query = query.filter(event_log.timestamp <= parsed_end)

    total = query.count()

    rows = (
        query.order_by(event_log.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    alert_list = []
    for ev, d_name, r_name in rows:
        eff_room_name = r_name
        if not eff_room_name and ev.room_id:
            r_obj = db.get(rooms, ev.room_id)
            if r_obj:
                eff_room_name = r_obj.name

        alert_list.append(
            AlertResponse(
                event_id=ev.event_id,
                dev_id=ev.dev_id,
                dev_name=d_name or (ev.dev_id if ev.dev_id else None),
                room_id=ev.room_id,
                room_name=eff_room_name,
                metric=ev.metric,
                severity=ev.severity,
                value=ev.value,
                threshold=ev.threshold,
                timestamp=ev.timestamp,
                resolved_at=ev.resolved_at,
                message=ev.message,
            )
        )

    return AlertListResponse(total=total, alerts=alert_list)
