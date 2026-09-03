# app/routers/rooms.py
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from databasev5 import get_db
from modelsv5 import User, dev_table, hub_table, rooms, temperature_data
from schemasv5 import (
    RoomCreate, RoomUpdate, RoomResponse, RoomMapMarker, RoomMapResponse, FloorPlanUploadResponse,
    RoomSparklinePoint, RoomSparkline, RoomSparklinesResponse
)
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.core.config import FLOORPLAN_UPLOAD_DIR, STATIC_DIR, ALLOWED_FLOORPLAN_TYPES, ALLOWED_FLOORPLAN_EXTENSIONS, MAX_FLOORPLAN_FILE_SIZE
from app.routers.devices import _build_epoch_bucket_expr
from app.services.telemetry import get_latest_readings_for_devices

router = APIRouter(tags=["rooms"])


def resolve_static_disk_path(path_or_url: str) -> str:
    if path_or_url.startswith("/static/"):
        rel = path_or_url[len("/static/"):]
        return os.path.join(STATIC_DIR, rel.replace("/", os.sep))
    elif path_or_url.startswith("static/"):
        rel = path_or_url[len("static/"):]
        return os.path.join(STATIC_DIR, rel.replace("/", os.sep))
    elif os.path.isabs(path_or_url):
        return path_or_url
    else:
        return os.path.join(FLOORPLAN_UPLOAD_DIR, os.path.basename(path_or_url))


def remove_floor_plan_file(path_or_url: Optional[str]) -> None:
    if not path_or_url:
        return
    disk_path = resolve_static_disk_path(path_or_url)
    if os.path.exists(disk_path) and os.path.isfile(disk_path):
        try:
            os.remove(disk_path)
        except OSError as e:
            logging.warning(f"Could not remove old floor plan file '{disk_path}': {e}")


@router.get("/api/rooms", response_model=list[RoomResponse])
@limiter.limit("60/minute")
def list_rooms(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(rooms, func.count(dev_table.dev_id).label("device_count"))
        .outerjoin(dev_table, rooms.id == dev_table.room_id)
        .group_by(rooms.id)
        .order_by(rooms.name)
    )
    rows = db.execute(stmt).all()
    results = [
        RoomResponse(
            id=r.id,
            name=r.name,
            hub_id=r.hub_id,
            floor_plan_image_path=r.floor_plan_image_path,
            device_count=dev_count,
            created_at=r.created_at,
        )
        for r, dev_count in rows
    ]
    return results


@router.get("/api/rooms/sparklines", response_model=RoomSparklinesResponse)
@limiter.limit("60/minute")
def get_room_sparklines(
    request: Request,
    range: str = Query("6h"),
    max_points: int = Query(24, ge=5, le=1000),
    room_ids: Optional[list[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    valid_ranges = {"1h", "6h", "24h", "7d", "30d", "all"}
    if range not in valid_ranges:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid range '{range}'. Valid options: 1h, 6h, 24h, 7d, 30d, all",
        )

    now = datetime.now(UTC)
    end_dt = now
    if range == "1h":
        start_dt = now - timedelta(hours=1)
    elif range == "6h":
        start_dt = now - timedelta(hours=6)
    elif range == "24h":
        start_dt = now - timedelta(hours=24)
    elif range == "7d":
        start_dt = now - timedelta(days=7)
    elif range == "30d":
        start_dt = now - timedelta(days=30)
    elif range == "all":
        min_ts = db.query(func.min(temperature_data.timestamp)).scalar()
        if min_ts is None:
            start_dt = now
        else:
            start_dt = min_ts if min_ts.tzinfo is not None else min_ts.replace(tzinfo=UTC)

    duration_sec = max(1.0, (end_dt - start_dt).total_seconds())
    bucket_seconds = max(1, int(duration_sec / max_points))

    target_room_ids: Optional[list[str]] = None
    if room_ids is not None:
        target_room_ids = []
        for item in room_ids:
            for r_id in item.split(","):
                clean_id = r_id.strip()
                if clean_id and clean_id not in target_room_ids:
                    target_room_ids.append(clean_id)

    if target_room_ids is not None:
        result: dict[str, RoomSparkline] = {rid: RoomSparkline(points=[]) for rid in target_room_ids}
        for r in db.query(rooms.id).filter(rooms.id.in_(target_room_ids)).all():
            if r[0] not in result:
                result[r[0]] = RoomSparkline(points=[])
    else:
        result = {r[0]: RoomSparkline(points=[]) for r in db.query(rooms.id).all()}

    dialect_name = db.get_bind().dialect.name
    bucket_expr = _build_epoch_bucket_expr(dialect_name, temperature_data.timestamp, bucket_seconds)

    stmt_p1 = (
        select(
            dev_table.room_id.label("room_id"),
            dev_table.dev_id.label("dev_id"),
            bucket_expr,
            func.avg(temperature_data.temp).label("dev_temp"),
            func.avg(temperature_data.humid).label("dev_humid"),
        )
        .join(dev_table, temperature_data.dev_id == dev_table.dev_id)
        .where(
            dev_table.dev_type.in_(("TS", "AC", "ACC")),
            dev_table.room_id.is_not(None),
            temperature_data.timestamp.between(start_dt, end_dt),
        )
    )
    if target_room_ids is not None:
        stmt_p1 = stmt_p1.where(dev_table.room_id.in_(target_room_ids))

    stmt_p1 = stmt_p1.group_by(
        dev_table.room_id,
        dev_table.dev_id,
        bucket_expr,
    )

    cte = stmt_p1.cte("device_bucket_agg")

    stmt_p2 = (
        select(
            cte.c.room_id,
            cte.c.bucket_ts,
            func.max(cte.c.dev_temp).label("room_temp"),
            func.max(cte.c.dev_humid).label("room_humid"),
        )
        .group_by(cte.c.room_id, cte.c.bucket_ts)
        .order_by(cte.c.room_id.asc(), cte.c.bucket_ts.asc())
    )

    rows = db.execute(stmt_p2).all()

    for row in rows:
        rid = row.room_id
        if rid not in result:
            result[rid] = RoomSparkline(points=[])

        dt = datetime.fromtimestamp(int(float(row.bucket_ts)), tz=UTC)
        ts_str = dt.isoformat()

        temp_val = round(float(row.room_temp), 2) if row.room_temp is not None else None
        humid_val = round(float(row.room_humid), 2) if row.room_humid is not None else None

        result[rid].points.append(
            RoomSparklinePoint(
                timestamp=ts_str,
                temp=temp_val,
                humid=humid_val,
            )
        )

    return result


@router.post("/api/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_room(
    request: Request,
    payload: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    clean_name = payload.name.strip()
    existing = db.query(rooms).filter(rooms.name == clean_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room name already exists",
        )

    if payload.hub_id:
        hub = db.get(hub_table, payload.hub_id)
        if not hub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hub '{payload.hub_id}' not found",
            )

    room_id = f"room_{uuid.uuid4().hex[:12]}"
    new_room = rooms(
        id=room_id,
        name=clean_name,
        hub_id=payload.hub_id,
        floor_plan_image_path=payload.floor_plan_image_path,
        created_at=datetime.now(UTC),
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)

    return RoomResponse(
        id=new_room.id,
        name=new_room.name,
        hub_id=new_room.hub_id,
        floor_plan_image_path=new_room.floor_plan_image_path,
        device_count=0,
        created_at=new_room.created_at,
    )


@router.patch("/api/rooms/{room_id}", response_model=RoomResponse)
@limiter.limit("30/minute")
def update_room(
    request: Request,
    room_id: str,
    payload: RoomUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    if payload.name is not None:
        clean_name = payload.name.strip()
        existing = db.query(rooms).filter(rooms.name == clean_name, rooms.id != room_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room name already exists",
            )
        room.name = clean_name

    if payload.hub_id is not None:
        if payload.hub_id != "":
            hub = db.get(hub_table, payload.hub_id)
            if not hub:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hub '{payload.hub_id}' not found",
                )
            room.hub_id = payload.hub_id
        else:
            room.hub_id = None

    if payload.floor_plan_image_path is not None:
        room.floor_plan_image_path = payload.floor_plan_image_path

    db.commit()
    db.refresh(room)

    dev_count = db.query(dev_table).filter(dev_table.room_id == room.id).count()
    return RoomResponse(
        id=room.id,
        name=room.name,
        hub_id=room.hub_id,
        floor_plan_image_path=room.floor_plan_image_path,
        device_count=dev_count,
        created_at=room.created_at,
    )


@router.delete("/api/rooms/{room_id}")
@limiter.limit("30/minute")
def delete_room(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    assigned_devices = db.query(dev_table).filter(dev_table.room_id == room_id).count()
    if assigned_devices > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete room with assigned devices",
        )

    remove_floor_plan_file(room.floor_plan_image_path)
    db.delete(room)
    db.commit()
    return {"status": "deleted", "room_id": room_id}


@router.post("/api/rooms/{room_id}/floor-plan", response_model=FloorPlanUploadResponse)
@limiter.limit("30/minute")
def upload_floor_plan(
    request: Request,
    room_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found",
        )

    content_type = (file.content_type or "").lower().strip()
    ext = os.path.splitext(file.filename or "")[1].lower()

    if content_type not in ALLOWED_FLOORPLAN_TYPES and ext not in ALLOWED_FLOORPLAN_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed formats: PNG, JPEG, WebP, SVG.",
        )

    if ext in ALLOWED_FLOORPLAN_EXTENSIONS:
        file_ext = ext
    else:
        file_ext = ALLOWED_FLOORPLAN_TYPES.get(content_type, ".png")

    try:
        contents = file.file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {str(e)}",
        )

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(contents) > MAX_FLOORPLAN_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum limit of 5MB.",
        )

    clean_room_id = "".join(c for c in room_id if c.isalnum() or c in ("-", "_"))
    safe_filename = f"floorplan_{clean_room_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    dest_path = os.path.join(FLOORPLAN_UPLOAD_DIR, safe_filename)

    remove_floor_plan_file(room.floor_plan_image_path)

    try:
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logging.exception(f"Error saving floor plan file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save floor plan image to disk.",
        )

    public_url = f"/static/uploads/floorplans/{safe_filename}"
    room.floor_plan_image_path = public_url
    db.commit()
    db.refresh(room)

    return FloorPlanUploadResponse(
        room_id=room.id,
        floor_plan_url=public_url,
        message="Floor plan uploaded successfully",
    )


@router.get("/api/rooms/{room_id}/map", response_model=RoomMapResponse)
@limiter.limit("60/minute")
def get_room_map(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.execute(
        select(rooms).options(joinedload(rooms.devices)).where(rooms.id == room_id)
    ).unique().scalars().first()

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found",
        )

    has_image = False
    floor_plan_url = None
    if room.floor_plan_image_path:
        disk_path = resolve_static_disk_path(room.floor_plan_image_path)
        if os.path.exists(disk_path) and os.path.isfile(disk_path):
            has_image = True
            floor_plan_url = room.floor_plan_image_path

    devices = room.devices or []
    if not devices:
        return RoomMapResponse(
            room_id=room.id,
            room_name=room.name,
            has_image=has_image,
            floor_plan_url=floor_plan_url,
            devices=[],
        )

    readings = get_latest_readings_for_devices(db, devices)
    marker_list = []
    for d in devices:
        status_str = "active" if d.is_active else "inactive"
        marker_list.append(
            RoomMapMarker(
                dev_id=d.dev_id,
                dev_name=d.dev_name,
                dev_type=d.dev_type or "",
                marker_x=d.marker_x,
                marker_y=d.marker_y,
                is_active=d.is_active,
                status=status_str,
                latest_reading=readings.get(d.dev_id),
            )
        )

    return RoomMapResponse(
        room_id=room.id,
        room_name=room.name,
        has_image=has_image,
        floor_plan_url=floor_plan_url,
        devices=marker_list,
    )
