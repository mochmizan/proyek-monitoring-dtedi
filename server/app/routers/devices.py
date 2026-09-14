# app/routers/devices.py
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from databasev5 import get_db
from modelsv5 import (
    User, ats_data, ats_daily, ats_hourly, ats_monthly, device_threshold_config,
    dev_table, hub_table, rooms, temperature_data, temperature_daily,
    temperature_hourly, temperature_monthly,
)
from schemasv5 import DevicePairRequest, DeviceResponse, ThresholdConfigSchema, ThresholdUpdateRequest, TelemetryHistoryPoint, DeviceHistoryResponse
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.core.csrf import validate_csrf_request
from app.routers.alerts import parse_datetime_param
from app.dependencies import hub_auth_cache, stage_hub_heartbeat
from app.services.telemetry import get_latest_readings_for_devices
from app.services.presence import DEVICE_OFFLINE_WINDOW_SECONDS

router = APIRouter(tags=["devices"], dependencies=[Depends(validate_csrf_request)])


@router.post("/api/devices/{dev_id}/approve")
@limiter.limit("30/minute")
def approve_device(
    request: Request,
    dev_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    clean_id = dev_id.strip()
    device = db.query(dev_table).filter(
        or_(
            func.lower(dev_table.dev_id) == clean_id.lower(),
            dev_table.dev_name == clean_id,
        )
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.is_active = True
    db.commit()
    return {"status": "approved", "dev_id": device.dev_id}


@router.post("/api/devices/{dev_id}/pair", response_model=DeviceResponse)
@limiter.limit("30/minute")
def pair_device(
    request: Request,
    dev_id: str,
    payload: DevicePairRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    clean_id = dev_id.strip()
    device = db.query(dev_table).filter(
        or_(
            func.lower(dev_table.dev_id) == clean_id.lower(),
            dev_table.dev_name == clean_id,
        )
    ).first()
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

    # Synchronize hub_id with room's assigned hub if missing or unassigned
    if room.hub_id and (not device.hub_id or device.hub_id != room.hub_id):
        device.hub_id = room.hub_id

    if payload.warning_threshold is not None and payload.critical_threshold is not None:
        if (device.dev_type or "").upper() == "ATS":
            if payload.warning_threshold < payload.critical_threshold:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="For ATS devices (undervoltage), warning threshold must be greater than or equal to critical threshold",
                )
        else:
            if payload.warning_threshold > payload.critical_threshold:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Warning threshold cannot exceed critical threshold",
                )

        default_hyst = 0.2 if device.dev_type == "ATS" else 0.5
        thresh = db.get(device_threshold_config, device.dev_id)
        if thresh:
            thresh.warning = payload.warning_threshold
            thresh.critical = payload.critical_threshold
            thresh.hysteresis = payload.hysteresis if payload.hysteresis is not None else default_hyst
            thresh.debounce_seconds = payload.debounce_seconds if payload.debounce_seconds is not None else 60
        else:
            thresh = device_threshold_config(
                dev_id=device.dev_id,
                warning=payload.warning_threshold,
                critical=payload.critical_threshold,
                hysteresis=payload.hysteresis if payload.hysteresis is not None else default_hyst,
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
    clean_id = dev_id.strip()
    device = db.query(dev_table).filter(
        or_(
            func.lower(dev_table.dev_id) == clean_id.lower(),
            dev_table.dev_name == clean_id,
        )
    ).first()
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
    return {"status": "unpaired", "dev_id": device.dev_id, "is_active": False}


@router.put("/api/devices/{dev_id}/thresholds", response_model=ThresholdConfigSchema)
@limiter.limit("30/minute")
def update_device_thresholds(
    request: Request,
    dev_id: str,
    payload: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    clean_id = dev_id.strip()
    device = db.query(dev_table).filter(
        or_(
            func.lower(dev_table.dev_id) == clean_id.lower(),
            dev_table.dev_name == clean_id,
        )
    ).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found",
        )

    if (device.dev_type or "").upper() == "ATS":
        if payload.warning < payload.critical:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For ATS devices (undervoltage), warning threshold must be greater than or equal to critical threshold",
            )
    else:
        if payload.warning > payload.critical:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warning threshold cannot exceed critical threshold",
            )

    thresh = db.get(device_threshold_config, device.dev_id)
    if thresh:
        thresh.warning = payload.warning
        thresh.critical = payload.critical
        thresh.hysteresis = payload.hysteresis
        thresh.debounce_seconds = payload.debounce_seconds
    else:
        thresh = device_threshold_config(
            dev_id=device.dev_id,
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


def _build_epoch_bucket_expr(dialect_name: str, col, bucket_seconds: int):
    """
    Constructs a single-pass epoch bucket expression for SQL GROUP BY and SELECT.
    Returns integer Unix epoch seconds at the start of the bucket.
    """
    if dialect_name == "sqlite":
        epoch = func.unixepoch(col)
        if bucket_seconds > 1:
            return (cast(epoch / bucket_seconds, Integer) * bucket_seconds).label("bucket_ts")
        return epoch.label("bucket_ts")
    else:
        # PostgreSQL & generic ANSI SQL
        if bucket_seconds > 1:
            return cast(
                func.floor(func.extract("epoch", col) / bucket_seconds) * bucket_seconds,
                Integer,
            ).label("bucket_ts")
        return cast(func.extract("epoch", col), Integer).label("bucket_ts")


def _compute_time_window(
    db: Session,
    dev_type: str,
    dev_id: str,
    range_str: str,
    max_points: int,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> tuple[datetime, datetime, int]:
    """
    Determines start_dt, end_dt, and mathematically computes bucket_seconds
    without issuing full table scans or count() queries.
    """
    now = datetime.now(UTC)

    if start_time is not None or end_time is not None:
        end_dt = parse_datetime_param(end_time) if end_time else now
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=UTC)

        if start_time is not None:
            start_dt = parse_datetime_param(start_time)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=UTC)
        else:
            valid_ranges = {"6h", "24h", "7d", "30d", "3m", "1y", "all"}
            if range_str not in valid_ranges:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid range '{range_str}'. Valid options: 6h, 24h, 7d, 30d, 3m, 1y, all",
                )
            if range_str == "6h":
                start_dt = end_dt - timedelta(hours=6)
            elif range_str == "24h":
                start_dt = end_dt - timedelta(hours=24)
            elif range_str == "7d":
                start_dt = end_dt - timedelta(days=7)
            elif range_str == "30d":
                start_dt = end_dt - timedelta(days=30)
            elif range_str == "3m":
                from app.services.telemetry_retention import _shift_months
                start_dt = _shift_months(end_dt, -3)
            elif range_str == "1y":
                from app.services.telemetry_retention import _shift_months
                start_dt = _shift_months(end_dt, -12)
            elif range_str == "all":
                tables = (temperature_data, temperature_hourly, temperature_daily, temperature_monthly) if dev_type in ("TS", "AC", "ACC") else (ats_data, ats_hourly, ats_daily, ats_monthly)
                timestamps = [table.timestamp if table in (temperature_data, ats_data) else table.bucket_start for table in tables]
                minima = [db.query(func.min(column)).filter(table.dev_id == dev_id).scalar() for table, column in zip(tables, timestamps)]
                min_ts = min((value for value in minima if value is not None), default=None)
                if min_ts is None:
                    return now, now, 1
                start_dt = min_ts if min_ts.tzinfo is not None else min_ts.replace(tzinfo=UTC)

        if start_dt > end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_time must be earlier than or equal to end_time",
            )
    else:
        valid_ranges = {"6h", "24h", "7d", "30d", "3m", "1y", "all"}
        if range_str not in valid_ranges:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid range '{range_str}'. Valid options: 6h, 24h, 7d, 30d, 3m, 1y, all",
            )
        end_dt = now
        if range_str == "6h":
            start_dt = now - timedelta(hours=6)
        elif range_str == "24h":
            start_dt = now - timedelta(hours=24)
        elif range_str == "7d":
            start_dt = now - timedelta(days=7)
        elif range_str == "30d":
            start_dt = now - timedelta(days=30)
        elif range_str == "3m":
            from app.services.telemetry_retention import _shift_months
            start_dt = _shift_months(now, -3)
        elif range_str == "1y":
            from app.services.telemetry_retention import _shift_months
            start_dt = _shift_months(now, -12)
        elif range_str == "all":
            tables = (temperature_data, temperature_hourly, temperature_daily, temperature_monthly) if dev_type in ("TS", "AC", "ACC") else (ats_data, ats_hourly, ats_daily, ats_monthly)
            timestamps = [table.timestamp if table in (temperature_data, ats_data) else table.bucket_start for table in tables]
            minima = [db.query(func.min(column)).filter(table.dev_id == dev_id).scalar() for table, column in zip(tables, timestamps)]
            min_ts = min((value for value in minima if value is not None), default=None)
            if min_ts is None:
                return now, now, 1
            start_dt = min_ts if min_ts.tzinfo is not None else min_ts.replace(tzinfo=UTC)

    duration_sec = max(1.0, (end_dt - start_dt).total_seconds())
    bucket_seconds = max(1, int(duration_sec // max_points))
    return start_dt, end_dt, bucket_seconds


def _downsample_ts(
    db: Session,
    dev_id: str,
    start_dt: datetime,
    end_dt: datetime,
    bucket_seconds: int,
) -> list[TelemetryHistoryPoint]:
    """Single-pass TS downsampling with min/max envelopes."""
    dialect_name = db.get_bind().dialect.name
    bucket_expr = _build_epoch_bucket_expr(dialect_name, temperature_data.timestamp, bucket_seconds)

    rows = (
        db.query(
            bucket_expr,
            func.avg(temperature_data.temp).label("temp"),
            func.min(temperature_data.temp).label("temp_min"),
            func.max(temperature_data.temp).label("temp_max"),
            func.avg(temperature_data.humid).label("humid"),
            func.min(temperature_data.humid).label("humid_min"),
            func.max(temperature_data.humid).label("humid_max"),
        )
        .filter(
            temperature_data.dev_id == dev_id,
            temperature_data.timestamp >= start_dt,
            temperature_data.timestamp <= end_dt,
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )

    points: list[TelemetryHistoryPoint] = []
    for r in rows:
        points.append(
            TelemetryHistoryPoint(
                timestamp=datetime.fromtimestamp(int(float(r.bucket_ts)), tz=UTC),
                temp=round(float(r.temp), 2) if r.temp is not None else None,
                temp_min=round(float(r.temp_min), 2) if r.temp_min is not None else None,
                temp_max=round(float(r.temp_max), 2) if r.temp_max is not None else None,
                humid=round(float(r.humid), 2) if r.humid is not None else None,
                humid_min=round(float(r.humid_min), 2) if r.humid_min is not None else None,
                humid_max=round(float(r.humid_max), 2) if r.humid_max is not None else None,
            )
        )
    return points


def _downsample_ats(
    db: Session,
    dev_id: str,
    start_dt: datetime,
    end_dt: datetime,
    bucket_seconds: int,
) -> list[TelemetryHistoryPoint]:
    """Single-pass ATS downsampling with min/max envelopes and state aggregation."""
    dialect_name = db.get_bind().dialect.name
    bucket_expr = _build_epoch_bucket_expr(dialect_name, ats_data.timestamp, bucket_seconds)

    rows = (
        db.query(
            bucket_expr,
            func.avg(ats_data.pln).label("pln"),
            func.min(ats_data.pln).label("pln_min"),
            func.max(ats_data.pln).label("pln_max"),
            func.avg(ats_data.genset).label("genset"),
            func.min(ats_data.genset).label("genset_min"),
            func.max(ats_data.genset).label("genset_max"),
            func.avg(ats_data.aki).label("aki"),
            func.min(ats_data.aki).label("aki_min"),
            func.max(ats_data.aki).label("aki_max"),
            func.max(ats_data.state).label("state"),
        )
        .filter(
            ats_data.dev_id == dev_id,
            ats_data.timestamp >= start_dt,
            ats_data.timestamp <= end_dt,
        )
        .group_by(bucket_expr)
        .order_by(bucket_expr.asc())
        .all()
    )

    points: list[TelemetryHistoryPoint] = []
    for r in rows:
        points.append(
            TelemetryHistoryPoint(
                timestamp=datetime.fromtimestamp(int(float(r.bucket_ts)), tz=UTC),
                pln=round(float(r.pln), 2) if r.pln is not None else None,
                pln_min=round(float(r.pln_min), 2) if r.pln_min is not None else None,
                pln_max=round(float(r.pln_max), 2) if r.pln_max is not None else None,
                genset=round(float(r.genset), 2) if r.genset is not None else None,
                genset_min=round(float(r.genset_min), 2) if r.genset_min is not None else None,
                genset_max=round(float(r.genset_max), 2) if r.genset_max is not None else None,
                aki=round(float(r.aki), 2) if r.aki is not None else None,
                aki_min=round(float(r.aki_min), 2) if r.aki_min is not None else None,
                aki_max=round(float(r.aki_max), 2) if r.aki_max is not None else None,
                state=r.state,
            )
        )
    return points


def _calendar_bucket(dialect: str, column, resolution: str):
    if dialect == "sqlite":
        fmt = {"hour": "%Y-%m-%d %H:00:00", "day": "%Y-%m-%d 00:00:00", "month": "%Y-%m-01 00:00:00"}[resolution]
        return func.strftime(fmt, column).label("bucket_start")
    return func.date_trunc(resolution, column).label("bucket_start")


def _tiered_history(db: Session, dev_id: str, kind: str, start_dt: datetime, end_dt: datetime, resolution: str) -> list[TelemetryHistoryPoint]:
    raw = temperature_data if kind == "temperature" else ats_data
    tiers = (temperature_hourly, temperature_daily, temperature_monthly) if kind == "temperature" else (ats_hourly, ats_daily, ats_monthly)
    metrics = ("temp", "humid") if kind == "temperature" else ("pln", "genset", "aki")
    combined: dict[datetime, dict] = {}
    dialect = db.get_bind().dialect.name
    for table in (raw, *tiers):
        time_col = table.timestamp if table is raw else table.bucket_start
        bucket = _calendar_bucket(dialect, time_col, resolution)
        columns = [bucket]
        for metric in metrics:
            if table is raw:
                columns.extend([func.sum(getattr(table, metric)), func.count(getattr(table, metric)), func.min(getattr(table, metric)), func.max(getattr(table, metric))])
            else:
                columns.extend([func.sum(getattr(table, f"{metric}_sum")), func.sum(getattr(table, f"{metric}_count")), func.min(getattr(table, f"{metric}_min")), func.max(getattr(table, f"{metric}_max"))])
        if kind == "ats":
            columns.append(func.max(table.state if table is raw else table.last_state))
        rows = db.query(*columns).filter(table.dev_id == dev_id, time_col >= start_dt, time_col <= end_dt).group_by(bucket).all()
        for row in rows:
            timestamp = row[0]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp).replace(tzinfo=UTC)
            else:
                timestamp = timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
            item = combined.setdefault(timestamp, {"state": None})
            offset = 1
            for metric in metrics:
                total, count, minimum, maximum = row[offset:offset + 4]
                item[f"{metric}_sum"] = item.get(f"{metric}_sum", 0.0) + float(total or 0)
                item[f"{metric}_count"] = item.get(f"{metric}_count", 0) + int(count or 0)
                minima = [value for value in (item.get(f"{metric}_min"), minimum) if value is not None]
                maxima = [value for value in (item.get(f"{metric}_max"), maximum) if value is not None]
                item[f"{metric}_min"] = min(minima) if minima else None
                item[f"{metric}_max"] = max(maxima) if maxima else None
                offset += 4
            if kind == "ats" and row[offset] is not None:
                item["state"] = row[offset]
    points = []
    for timestamp, item in sorted(combined.items()):
        values = {"timestamp": timestamp, "state": item["state"]}
        for metric in metrics:
            count = item.get(f"{metric}_count", 0)
            values[metric] = round(item[f"{metric}_sum"] / count, 2) if count else None
            values[f"{metric}_min"] = round(float(item[f"{metric}_min"]), 2) if item[f"{metric}_min"] is not None else None
            values[f"{metric}_max"] = round(float(item[f"{metric}_max"]), 2) if item[f"{metric}_max"] is not None else None
        points.append(TelemetryHistoryPoint(**values))
    return points


@router.get("/api/devices/{dev_id}/history", response_model=DeviceHistoryResponse)
@limiter.limit("60/minute")
def get_device_history(
    request: Request,
    dev_id: str,
    range: str = Query("24h"),
    max_points: int = Query(1000, ge=10, le=5000),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = (
        db.query(dev_table)
        .filter(or_(dev_table.dev_id == dev_id, dev_table.dev_name == dev_id))
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    start_dt, end_dt, bucket_sec = _compute_time_window(
        db=db,
        dev_type=device.dev_type or "",
        dev_id=device.dev_id,
        range_str=range,
        max_points=max_points,
        start_time=start_time,
        end_time=end_time,
    )

    # Short-circuit if device has no time window / no data
    if start_dt == end_dt and range == "all" and start_time is None and end_time is None:
        return DeviceHistoryResponse(
            dev_id=device.dev_id,
            dev_type=device.dev_type or "",
            range=range,
            total_points=0,
            points=[],
            bucket_seconds=bucket_sec,
        )

    resolution = {"3m": "hour", "1y": "day", "all": "month"}.get(range, "raw") if start_time is None and end_time is None else "raw"
    if resolution != "raw":
        kind = "temperature" if device.dev_type in ("TS", "AC", "ACC") else "ats"
        points = _tiered_history(db, device.dev_id, kind, start_dt, end_dt, resolution) if device.dev_type in ("TS", "AC", "ACC", "ATS") else []
        bucket_sec = {"hour": 3600, "day": 86400, "month": None}[resolution]
    elif device.dev_type in ("TS", "AC", "ACC"):
        points = _downsample_ts(db, device.dev_id, start_dt, end_dt, bucket_sec)
    elif device.dev_type == "ATS":
        points = _downsample_ats(db, device.dev_id, start_dt, end_dt, bucket_sec)
    else:
        points = []

    effective_range = "custom" if (start_time is not None or end_time is not None) else range

    return DeviceHistoryResponse(
        dev_id=device.dev_id,
        dev_type=device.dev_type or "",
        range=effective_range,
        total_points=len(points),
        points=points,
        bucket_seconds=bucket_sec,
        resolution=resolution,
    )


@router.get("/api/devices/{dev_id}", response_model=DeviceResponse)
@limiter.limit("60/minute")
def get_device(
    request: Request,
    dev_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(dev_table)
        .options(
            selectinload(dev_table.threshold_config),
            selectinload(dev_table.room),
        )
        .where(or_(dev_table.dev_id == dev_id, dev_table.dev_name == dev_id))
    )
    device = db.execute(stmt).scalars().first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found",
        )

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=DEVICE_OFFLINE_WINDOW_SECONDS)
    d_seen = device.last_seen if (device.last_seen and device.last_seen.tzinfo is not None) else (device.last_seen.replace(tzinfo=UTC) if device.last_seen else None)
    if not device.is_active:
        computed_status = "pending"
    elif d_seen and d_seen >= cutoff:
        computed_status = "online"
    else:
        computed_status = "offline"

    thresh_schema = None
    if device.threshold_config:
        thresh_schema = ThresholdConfigSchema(
            warning=device.threshold_config.warning,
            critical=device.threshold_config.critical,
            hysteresis=device.threshold_config.hysteresis,
            debounce_seconds=device.threshold_config.debounce_seconds,
        )

    readings = get_latest_readings_for_devices(db, [device])
    latest_reading = readings.get(device.dev_id)

    return DeviceResponse(
        dev_id=device.dev_id,
        dev_name=device.dev_name,
        dev_type=device.dev_type,
        hub_id=device.hub_id,
        is_active=device.is_active,
        status=computed_status,
        last_seen=device.last_seen,
        room_id=device.room_id,
        marker_x=device.marker_x,
        marker_y=device.marker_y,
        created_at=device.created_at,
        threshold_config=thresh_schema,
        latest_reading=latest_reading,
    )


@router.get("/api/devices")
@limiter.limit("60/minute")
def get_devices(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    dev_type_filter: Optional[str] = Query(None, alias="dev_type"),
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
        entry = hub_auth_cache.get_or_load(x_hub_id, db)
        if not entry or not entry.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
            )
        if not secrets.compare_digest(entry.hub_key, x_hub_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: API Key Hub tidak cocok!",
            )

        registered_hub = db.get(hub_table, x_hub_id)
        if not registered_hub or not registered_hub.is_active:
            hub_auth_cache.invalidate(x_hub_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
            )

        stage_hub_heartbeat(registered_hub)
        if db.dirty:
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
    override = getattr(request.app, "dependency_overrides", {}).get(get_current_user)
    if override:
        _user = override()
    else:
        _user = get_current_user(request, db)

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=DEVICE_OFFLINE_WINDOW_SECONDS)

    stmt = (
        select(dev_table)
        .options(
            selectinload(dev_table.threshold_config),
            selectinload(dev_table.room),
        )
    )
    if status_filter == "pending":
        stmt = stmt.where(dev_table.is_active == False)  # noqa: E712
    elif status_filter == "active":
        stmt = stmt.where(dev_table.is_active == True)  # noqa: E712
    elif status_filter in ("all", None):
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter. Use 'pending', 'active', or 'all'.",
        )

    if dev_type_filter is not None:
        dt = dev_type_filter.strip().upper()
        if dt not in ("ATS", "AC", "ACC", "TS"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dev_type filter. Use ATS, AC, ACC, or TS.")
        stmt = stmt.where(dev_table.dev_type == dt)
    devices = db.execute(stmt).scalars().all()
    readings = get_latest_readings_for_devices(db, devices)
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
                latest_reading=readings.get(d.dev_id),
            )
        )
    return results

