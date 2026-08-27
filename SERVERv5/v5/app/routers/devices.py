# app/routers/devices.py
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import dev_table, hub_table, rooms, device_threshold_config, temperature_data, ats_data, event_log, User
from schemasv5 import DevicePairRequest, DeviceResponse, ThresholdConfigSchema, ThresholdUpdateRequest, TelemetryHistoryPoint, DeviceHistoryResponse
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.services.presence import prune_stale_pending, update_device_presence_on_list

router = APIRouter(tags=["devices"])


@router.post("/api/devices/{dev_id}/approve")
@limiter.limit("30/minute")
def approve_device(
    request: Request,
    dev_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")

    device.is_active = True
    db.commit()
    return {"status": "approved", "dev_id": dev_id}


@router.post("/api/devices/{dev_id}/pair", response_model=DeviceResponse)
@limiter.limit("30/minute")
def pair_device(
    request: Request,
    dev_id: str,
    payload: DevicePairRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found",
        )

    room = db.get(rooms, payload.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{payload.room_id}' not found",
        )

    device.dev_name = payload.dev_name.strip()
    device.room_id = payload.room_id
    device.marker_x = payload.marker_x
    device.marker_y = payload.marker_y
    device.is_active = True

    if payload.warning_threshold is not None and payload.critical_threshold is not None:
        thresh = db.get(device_threshold_config, dev_id)
        if thresh:
            thresh.warning = payload.warning_threshold
            thresh.critical = payload.critical_threshold
            thresh.hysteresis = payload.hysteresis if payload.hysteresis is not None else 0.5
            thresh.debounce_seconds = payload.debounce_seconds if payload.debounce_seconds is not None else 60
        else:
            thresh = device_threshold_config(
                dev_id=dev_id,
                warning=payload.warning_threshold,
                critical=payload.critical_threshold,
                hysteresis=payload.hysteresis if payload.hysteresis is not None else 0.5,
                debounce_seconds=payload.debounce_seconds if payload.debounce_seconds is not None else 60,
            )
            db.add(thresh)

    db.commit()
    db.refresh(device)

    thresh_schema = None
    if device.threshold_config:
        thresh_schema = ThresholdConfigSchema(
            warning=device.threshold_config.warning,
            critical=device.threshold_config.critical,
            hysteresis=device.threshold_config.hysteresis,
            debounce_seconds=device.threshold_config.debounce_seconds,
        )

    return DeviceResponse(
        dev_id=device.dev_id,
        dev_name=device.dev_name,
        dev_type=device.dev_type,
        hub_id=device.hub_id,
        is_active=device.is_active,
        room_id=device.room_id,
        marker_x=device.marker_x,
        marker_y=device.marker_y,
        created_at=device.created_at,
        threshold_config=thresh_schema,
    )


@router.post("/api/devices/{dev_id}/unpair")
@limiter.limit("30/minute")
def unpair_device(
    request: Request,
    dev_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found",
        )

    device.room_id = None
    device.marker_x = None
    device.marker_y = None
    device.is_active = False

    db.commit()
    return {"status": "unpaired", "dev_id": dev_id, "is_active": False}


@router.put("/api/devices/{dev_id}/thresholds", response_model=ThresholdConfigSchema)
@limiter.limit("30/minute")
def update_device_thresholds(
    request: Request,
    dev_id: str,
    payload: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found",
        )

    if payload.warning > payload.critical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Warning threshold cannot exceed critical threshold",
        )

    thresh = db.get(device_threshold_config, dev_id)
    if thresh:
        thresh.warning = payload.warning
        thresh.critical = payload.critical
        thresh.hysteresis = payload.hysteresis
        thresh.debounce_seconds = payload.debounce_seconds
    else:
        thresh = device_threshold_config(
            dev_id=dev_id,
            warning=payload.warning,
            critical=payload.critical,
            hysteresis=payload.hysteresis,
            debounce_seconds=payload.debounce_seconds,
        )
        db.add(thresh)

    db.commit()
    db.refresh(thresh)

    return ThresholdConfigSchema(
        warning=thresh.warning,
        critical=thresh.critical,
        hysteresis=thresh.hysteresis,
        debounce_seconds=thresh.debounce_seconds,
    )


@router.get("/api/devices/{dev_id}/history", response_model=DeviceHistoryResponse)
@limiter.limit("60/minute")
def get_device_history(
    request: Request,
    dev_id: str,
    range: str = Query("24h"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    valid_ranges = {"6h", "24h", "7d", "30d", "all"}
    if range not in valid_ranges:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid range '{range}'. Valid options: 6h, 24h, 7d, 30d, all",
        )

    now = datetime.now(UTC)
    cutoff = None
    if range == "6h":
        cutoff = now - timedelta(hours=6)
    elif range == "24h":
        cutoff = now - timedelta(hours=24)
    elif range == "7d":
        cutoff = now - timedelta(days=7)
    elif range == "30d":
        cutoff = now - timedelta(days=30)
    elif range == "all":
        cutoff = None

    points: list[TelemetryHistoryPoint] = []

    def _bucket_seconds() -> int:
        window_end = now
        if cutoff is not None:
            window_start = cutoff
        else:
            if device.dev_type in ("TS", "AC", "ACC"):
                window_start = db.query(func.min(temperature_data.timestamp)).filter(
                    temperature_data.dev_id == dev_id
                ).scalar() or now
            else:
                window_start = db.query(func.min(ats_data.timestamp)).filter(
                    ats_data.dev_id == dev_id
                ).scalar() or now
            if window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=UTC)
        return max(1, int((window_end - window_start).total_seconds()) // 1000)

    def _epoch_expr(col):
        if db.get_bind().dialect.name == "sqlite":
            return cast(func.strftime("%s", col), Integer)
        return cast(func.extract("epoch", col), Integer)

    if device.dev_type in ("TS", "AC", "ACC"):
        q = db.query(temperature_data).filter(temperature_data.dev_id == dev_id)
        if cutoff is not None:
            q = q.filter(temperature_data.timestamp >= cutoff)
        if q.count() <= 1000:
            rows = q.order_by(temperature_data.timestamp.desc()).limit(1000).all()
            rows.reverse()
            for r in rows:
                ts = r.timestamp if (r.timestamp and r.timestamp.tzinfo is not None) else (r.timestamp.replace(tzinfo=UTC) if r.timestamp else None)
                points.append(
                    TelemetryHistoryPoint(
                        timestamp=ts,
                        temp=r.temp,
                        humid=r.humid,
                    )
                )
        else:
            bucket_sec = _bucket_seconds()
            epoch = _epoch_expr(temperature_data.timestamp)
            bucket_expr = cast(epoch / bucket_sec, Integer)
            rows = (
                q.with_entities(
                    bucket_expr.label("b"),
                    func.avg(temperature_data.temp).label("temp"),
                    func.avg(temperature_data.humid).label("humid"),
                    func.avg(epoch).label("ts"),
                )
                .group_by(bucket_expr)
                .order_by(bucket_expr)
                .all()
            )
            for r in rows:
                points.append(
                    TelemetryHistoryPoint(
                        timestamp=datetime.fromtimestamp(float(r.ts), tz=UTC),
                        temp=r.temp,
                        humid=r.humid,
                    )
                )
    elif device.dev_type == "ATS":
        q = db.query(ats_data).filter(ats_data.dev_id == dev_id)
        if cutoff is not None:
            q = q.filter(ats_data.timestamp >= cutoff)
        if q.count() <= 1000:
            rows = q.order_by(ats_data.timestamp.desc()).limit(1000).all()
            rows.reverse()
            for r in rows:
                ts = r.timestamp if (r.timestamp and r.timestamp.tzinfo is not None) else (r.timestamp.replace(tzinfo=UTC) if r.timestamp else None)
                points.append(
                    TelemetryHistoryPoint(
                        timestamp=ts,
                        pln=r.pln,
                        genset=r.genset,
                        aki=r.aki,
                        state=r.state,
                    )
                )
        else:
            bucket_sec = _bucket_seconds()
            epoch = _epoch_expr(ats_data.timestamp)
            bucket_expr = cast(epoch / bucket_sec, Integer)
            rows = (
                q.with_entities(
                    bucket_expr.label("b"),
                    func.avg(ats_data.pln).label("pln"),
                    func.avg(ats_data.genset).label("genset"),
                    func.avg(ats_data.aki).label("aki"),
                    func.max(ats_data.state).label("state"),
                    func.avg(epoch).label("ts"),
                )
                .group_by(bucket_expr)
                .order_by(bucket_expr)
                .all()
            )
            for r in rows:
                points.append(
                    TelemetryHistoryPoint(
                        timestamp=datetime.fromtimestamp(float(r.ts), tz=UTC),
                        pln=r.pln,
                        genset=r.genset,
                        aki=r.aki,
                        state=r.state,
                    )
                )

    return DeviceHistoryResponse(
        dev_id=device.dev_id,
        dev_type=device.dev_type or "",
        range=range,
        total_points=len(points),
        points=points,
    )


@router.get("/api/devices")
@limiter.limit("60/minute")
def get_devices(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    x_hub_id: Optional[str] = Header(None, alias="X-Hub-ID"),
    x_hub_key: Optional[str] = Header(None, alias="X-Hub-Key"),
    db: Session = Depends(get_db),
):
    # 1. Edge Hub authentication path
    if x_hub_id is not None or x_hub_key is not None:
        if not x_hub_id or not x_hub_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub ID dan Key harus disertakan!",
            )
        registered_hub = db.get(hub_table, x_hub_id)
        if not registered_hub or not registered_hub.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
            )
        registered_hub_key = registered_hub.hub_key or ""
        if not secrets.compare_digest(registered_hub_key, x_hub_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: API Key Hub tidak cocok!",
            )

        registered_hub.last_seen = datetime.now(UTC)
        db.commit()

        devices = db.query(dev_table).filter(
            dev_table.is_active == True,  # noqa: E712
            dev_table.hub_id == registered_hub.hub_id,
        ).all()

        return [
            {
                "DEV_ID": d.dev_id,
                "DEV_NAME": d.dev_name,
                "DEV_TYPE": d.dev_type,
                "HUB_NAME": d.hub_id,
            }
            for d in devices
        ]

    # 2. User session authentication path
    from auth import get_current_user
    user = get_current_user(request, db)

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=25)
    prune_stale_pending(db, cutoff)
    update_device_presence_on_list(db, now_utc, cutoff)

    query = db.query(dev_table)
    if status_filter == "pending":
        query = query.filter(dev_table.is_active == False)  # noqa: E712
    elif status_filter == "active":
        query = query.filter(dev_table.is_active == True)  # noqa: E712
    elif status_filter == "all" or status_filter is None:
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter. Use 'pending', 'active', or 'all'.",
        )

    devices = query.all()
    results = []
    for d in devices:
        thresh_schema = None
        if d.threshold_config:
            thresh_schema = ThresholdConfigSchema(
                warning=d.threshold_config.warning,
                critical=d.threshold_config.critical,
                hysteresis=d.threshold_config.hysteresis,
                debounce_seconds=d.threshold_config.debounce_seconds,
            )

        d_seen = d.last_seen if (d.last_seen and d.last_seen.tzinfo is not None) else (d.last_seen.replace(tzinfo=UTC) if d.last_seen else None)
        if not d.is_active:
            computed_status = "pending"
        elif d_seen and d_seen >= cutoff:
            computed_status = "online"
        else:
            computed_status = "offline"

        results.append(
            DeviceResponse(
                dev_id=d.dev_id,
                dev_name=d.dev_name,
                dev_type=d.dev_type,
                hub_id=d.hub_id,
                is_active=d.is_active,
                status=computed_status,
                last_seen=d.last_seen,
                room_id=d.room_id,
                marker_x=d.marker_x,
                marker_y=d.marker_y,
                created_at=d.created_at,
                threshold_config=thresh_schema,
            )
        )
    return results
