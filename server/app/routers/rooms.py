# app/routers/rooms.py
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from databasev5 import get_db
from modelsv5 import User, dev_table, hub_table, rooms, temperature_data, ats_data, data_table
from schemasv5 import RoomCreate, RoomUpdate, RoomResponse, RoomMapMarker, RoomMapResponse, FloorPlanUploadResponse
from auth import get_current_user, require_role
from app.core.rate_limit import limiter
from app.core.config import FLOORPLAN_UPLOAD_DIR, STATIC_DIR, ALLOWED_FLOORPLAN_TYPES, ALLOWED_FLOORPLAN_EXTENSIONS, MAX_FLOORPLAN_FILE_SIZE

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

    marker_list = []
    for d in devices:
        status_str = "active" if d.is_active else "inactive"
        latest_reading = None

        if d.dev_type == "ATS":
            ats_row = (
                db.query(ats_data)
                .filter(ats_data.dev_id == d.dev_id)
                .order_by(ats_data.timestamp.desc())
                .first()
            )
            if ats_row:
                ts_dt = ats_row.timestamp
                latest_reading = {
                    "timestamp": ts_dt.isoformat() if hasattr(ts_dt, "isoformat") else (str(ts_dt) if ts_dt else None),
                    "state": ats_row.state,
                    "pln": ats_row.pln,
                    "genset": ats_row.genset,
                    "aki": ats_row.aki,
                    "rem_hour": ats_row.rem_hour,
                    "rem_min": ats_row.rem_min,
                    "rem_sec": ats_row.rem_sec,
                    "auto_mode": ats_row.auto_mode,
                    "emergency": ats_row.emergency,
                }
        elif d.dev_type in ("TS", "AC", "ACC"):
            ts_row = (
                db.query(temperature_data)
                .filter(temperature_data.dev_id == d.dev_id)
                .order_by(temperature_data.timestamp.desc())
                .first()
            )
            if ts_row:
                ts_dt = ts_row.timestamp
                latest_reading = {
                    "timestamp": ts_dt.isoformat() if hasattr(ts_dt, "isoformat") else (str(ts_dt) if ts_dt else None),
                    "temp": ts_row.temp,
                    "humid": ts_row.humid,
                }
            if d.dev_type in ("AC", "ACC"):
                dt_row = (
                    db.query(data_table)
                    .filter(data_table.dev_id == d.dev_id)
                    .order_by(data_table.timestamp.desc())
                    .first()
                )
                if dt_row and dt_row.payload and isinstance(dt_row.payload, dict):
                    p = dt_row.payload
                    if latest_reading is None:
                        latest_reading = {}
                        ts_dt = dt_row.timestamp
                        if ts_dt:
                            latest_reading["timestamp"] = ts_dt.isoformat() if hasattr(ts_dt, "isoformat") else str(ts_dt)
                    for k in ("AC1_POWER", "AC1_TEMP", "AC2_POWER", "AC2_TEMP"):
                        val = p.get(k)
                        if val is None:
                            val = p.get(k.lower())
                        if val is not None:
                            if "POWER" in k and isinstance(val, str):
                                val = val.upper()
                            latest_reading[k] = val
                            latest_reading[k.lower()] = val

        # If no reading found yet, check data_table
        if latest_reading is None:
            dt_row = (
                db.query(data_table)
                .filter(data_table.dev_id == d.dev_id)
                .order_by(data_table.timestamp.desc())
                .first()
            )
            if dt_row:
                p = dt_row.payload or {}
                payload_copy = dict(p) if isinstance(p, dict) else {}
                if "timestamp" not in payload_copy and dt_row.timestamp:
                    ts_dt = dt_row.timestamp
                    payload_copy["timestamp"] = ts_dt.isoformat() if hasattr(ts_dt, "isoformat") else str(ts_dt)
                latest_reading = payload_copy

        marker_list.append(
            RoomMapMarker(
                dev_id=d.dev_id,
                dev_name=d.dev_name,
                dev_type=d.dev_type or "",
                marker_x=d.marker_x,
                marker_y=d.marker_y,
                is_active=d.is_active,
                status=status_str,
                latest_reading=latest_reading,
            )
        )

    return RoomMapResponse(
        room_id=room.id,
        room_name=room.name,
        has_image=has_image,
        floor_plan_url=floor_plan_url,
        devices=marker_list,
    )
