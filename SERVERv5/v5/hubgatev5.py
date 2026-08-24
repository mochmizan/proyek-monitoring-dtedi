# hubgatev5.py - Main Gateway API
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
load_dotenv()



from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request, Response, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import ValidationError

# IMPORT MODULE V5
from databasev5 import get_db
from modelsv5 import (
    data_table, dev_table, hub_table, pending_commands, temperature_data, ats_data,
    User, LoginAttempt, rooms, device_threshold_config, Room, DeviceThresholdConfig,
    event_log, EventLog
)
from schemasv5 import (
    IotPayload, UnapprovedDeviceAlert, HubRegisterPayload, ATSCommand, ACCommand, TSData, ATSData, ACData, ACCData,
    RoomCreate, RoomUpdate, RoomResponse, GatewayRoomAssign, DevicePairRequest,
    DeviceResponse, DevicePairResponse, ThresholdConfigSchema,
    RoomMapMarker, RoomMapResponse, FloorPlanUploadResponse,
    ThresholdUpdateRequest, AlertResponse, AlertListResponse,
    TelemetryHistoryPoint, DeviceHistoryResponse,
    HubDeviceSummary, HubResponse, HubPairRequest
)

# IMPORT AUTH MODULE V5
from auth import (
    SessionExpired,
    session_expired_handler,
    get_current_user,
    require_role,
    create_session,
    delete_session,
    handle_db_lockout,
    verify_password_safe
)
from schemas_auth import UserLoginPayload, UserResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ==========================================
# SETUP RATE LIMITER & FASTAPI
# ==========================================
def get_forwarded_address(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        parts = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        if parts:
            return parts[-1]
    return get_remote_address(request)

limiter = Limiter(key_func=get_forwarded_address)
api = FastAPI(title="HubGate V5 - Secure API Gateway")
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api.add_exception_handler(SessionExpired, session_expired_handler)

# CORS Middleware Setup
cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://example.com").strip()
if cors_origins_str:
    origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
    allow_credentials = True
    if "*" in origins:
        allow_credentials = False
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Static Upload Directory Setup (Milestone 3)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(BASE_DIR, "static"))
FLOORPLAN_UPLOAD_DIR = os.getenv("FLOORPLAN_UPLOAD_DIR", os.path.join(STATIC_DIR, "uploads", "floorplans"))
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(FLOORPLAN_UPLOAD_DIR, exist_ok=True)

api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ALLOWED_FLOORPLAN_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
ALLOWED_FLOORPLAN_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_FLOORPLAN_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def resolve_static_disk_path(path_or_url: str) -> str:
    """Helper to resolve a /static/... URL or relative/absolute path to local disk path."""
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
    """Helper to safely unlink floor plan file if it exists on disk."""
    if not path_or_url:
        return
    disk_path = resolve_static_disk_path(path_or_url)
    if os.path.exists(disk_path) and os.path.isfile(disk_path):
        try:
            os.remove(disk_path)
        except OSError as e:
            logging.warning(f"Could not remove old floor plan file '{disk_path}': {e}")


# ==========================================
# MIDDLEWARE & AUTHENTICATION DEPENDENCIES
# ==========================================


def verify_hub_identity(
    x_hub_id: str = Header(..., alias="X-Hub-ID"),
    x_hub_key: str = Header(..., alias="X-Hub-Key"),
    db: Session = Depends(get_db)
):
    """[V5] Memverifikasi Keabsahan Hub Pengirim via Database PostgreSQL."""
    registered_hub = db.get(hub_table, x_hub_id)

    if not registered_hub or not registered_hub.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!"
        )

    registered_hub_key = registered_hub.hub_key or ""
    if not secrets.compare_digest(registered_hub_key, x_hub_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Akses Ditolak: API Key Hub tidak cocok!"
        )

    # [V5 PRESENCE] Perbarui heartbeat terakhir Hub pada setiap permintaan berhasil
    registered_hub.last_seen = datetime.now(UTC)
    db.commit()

    return registered_hub


# ==========================================
# ENDPOINTS ADMIN (PROTECTED BY ROLE ADMIN)
# ==========================================

@api.post("/api/admin/hubs")
@limiter.limit("10/minute")
def register_new_hub(
    request: Request,
    payload: HubRegisterPayload, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin mendaftarkan Hub (Raspberry Pi) resmi baru ke Database."""
    exist = db.get(hub_table, payload.HUB_ID)
    if exist:
        raise HTTPException(status_code=400, detail="HUB_ID sudah terdaftar!")

    new_hub = hub_table(
        hub_id=payload.HUB_ID,
        hub_name=payload.HUB_NAME,
        hub_key=payload.HUB_KEY,
        is_active=True
    )
    db.add(new_hub)
    db.commit()
    return {"status": "hub_registered", "hub_id": payload.HUB_ID}


@api.post("/api/devices/{dev_id}/approve")
@limiter.limit("30/minute")
def approve_device(
    request: Request,
    dev_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin menyetujui perangkat IoT pending agar aktif."""
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")
    
    device.is_active = True
    db.commit()
    return {"status": "approved", "dev_id": dev_id}


# ==========================================
# ROOM MANAGEMENT ENDPOINTS (Milestone 2)
# ==========================================

@api.get("/api/rooms", response_model=list[RoomResponse])
@limiter.limit("60/minute")
def list_rooms(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[V5] List all rooms with assigned device count, associated hub, and floor plan path."""
    all_rooms = db.query(rooms).all()
    results = []
    for r in all_rooms:
        dev_count = db.query(dev_table).filter(dev_table.room_id == r.id).count()
        results.append(
            RoomResponse(
                id=r.id,
                name=r.name,
                hub_id=r.hub_id,
                floor_plan_image_path=r.floor_plan_image_path,
                device_count=dev_count,
                created_at=r.created_at
            )
        )
    return results


@api.post("/api/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_room(
    request: Request,
    payload: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin creates a new room with a unique name."""
    clean_name = payload.name.strip()
    existing = db.query(rooms).filter(rooms.name == clean_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room name already exists"
        )

    if payload.hub_id:
        hub = db.get(hub_table, payload.hub_id)
        if not hub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hub '{payload.hub_id}' not found"
            )

    room_id = f"room_{uuid.uuid4().hex[:12]}"
    new_room = rooms(
        id=room_id,
        name=clean_name,
        hub_id=payload.hub_id,
        floor_plan_image_path=payload.floor_plan_image_path,
        created_at=datetime.now(UTC)
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
        created_at=new_room.created_at
    )


@api.patch("/api/rooms/{room_id}", response_model=RoomResponse)
@limiter.limit("30/minute")
def update_room(
    request: Request,
    room_id: str,
    payload: RoomUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin updates room name, hub_id, or floor plan path."""
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    if payload.name is not None:
        clean_name = payload.name.strip()
        existing = db.query(rooms).filter(rooms.name == clean_name, rooms.id != room_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room name already exists"
            )
        room.name = clean_name

    if payload.hub_id is not None:
        if payload.hub_id != "":
            hub = db.get(hub_table, payload.hub_id)
            if not hub:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hub '{payload.hub_id}' not found"
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
        created_at=room.created_at
    )


@api.delete("/api/rooms/{room_id}")
@limiter.limit("30/minute")
def delete_room(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin deletes a room. Rejects if devices are assigned."""
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    assigned_devices = db.query(dev_table).filter(dev_table.room_id == room_id).count()
    if assigned_devices > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete room with assigned devices"
        )

    remove_floor_plan_file(room.floor_plan_image_path)
    db.delete(room)
    db.commit()
    return {"status": "deleted", "room_id": room_id}


# ==========================================
# FLOOR PLAN & MAP ENDPOINTS (Milestone 3)
# ==========================================

@api.post("/api/rooms/{room_id}/floor-plan", response_model=FloorPlanUploadResponse)
@limiter.limit("30/minute")
def upload_floor_plan(
    request: Request,
    room_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin uploads a floor plan image for a room (PNG, JPEG, WebP, SVG, up to 5MB). Replaces existing image."""
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found"
        )

    content_type = (file.content_type or "").lower().strip()
    ext = os.path.splitext(file.filename or "")[1].lower()

    if content_type not in ALLOWED_FLOORPLAN_TYPES and ext not in ALLOWED_FLOORPLAN_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed formats: PNG, JPEG, WebP, SVG."
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
            detail=f"Failed to read uploaded file: {str(e)}"
        )

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(contents) > MAX_FLOORPLAN_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum limit of 5MB."
        )

    # Secure server-side filename (prevents directory traversal)
    clean_room_id = "".join(c for c in room_id if c.isalnum() or c in ("-", "_"))
    safe_filename = f"floorplan_{clean_room_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    dest_path = os.path.join(FLOORPLAN_UPLOAD_DIR, safe_filename)

    # Remove old floor plan file if existed on disk
    remove_floor_plan_file(room.floor_plan_image_path)

    # Save new file
    try:
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logging.exception(f"Error saving floor plan file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save floor plan image to disk."
        )

    public_url = f"/static/uploads/floorplans/{safe_filename}"
    room.floor_plan_image_path = public_url
    db.commit()
    db.refresh(room)

    return FloorPlanUploadResponse(
        room_id=room.id,
        floor_plan_url=public_url,
        message="Floor plan uploaded successfully"
    )


@api.get("/api/rooms/{room_id}/map", response_model=RoomMapResponse)
@limiter.limit("60/minute")
def get_room_map(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[V5] Retrieve room floor plan URL and device marker coordinates with latest telemetry."""
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found"
        )

    has_image = False
    floor_plan_url = None
    if room.floor_plan_image_path:
        disk_path = resolve_static_disk_path(room.floor_plan_image_path)
        if os.path.exists(disk_path) and os.path.isfile(disk_path):
            has_image = True
            floor_plan_url = room.floor_plan_image_path

    # Gather assigned devices
    devices = db.query(dev_table).filter(dev_table.room_id == room_id).all()
    marker_list = []

    for d in devices:
        latest_reading = None
        status_str = "active" if d.is_active else "inactive"

        if d.dev_type == "TS":
            last_ts = (
                db.query(temperature_data)
                .filter(temperature_data.dev_id == d.dev_id)
                .order_by(temperature_data.timestamp.desc())
                .first()
            )
            if last_ts:
                latest_reading = {
                    "timestamp": last_ts.timestamp.isoformat() if last_ts.timestamp else None,
                    "temp": last_ts.temp,
                    "humid": last_ts.humid,
                }
        elif d.dev_type == "ATS":
            last_ats = (
                db.query(ats_data)
                .filter(ats_data.dev_id == d.dev_id)
                .order_by(ats_data.timestamp.desc())
                .first()
            )
            if last_ats:
                latest_reading = {
                    "timestamp": last_ats.timestamp.isoformat() if last_ats.timestamp else None,
                    "state": last_ats.state,
                    "pln": last_ats.pln,
                    "genset": last_ats.genset,
                    "aki": last_ats.aki,
                    "rem_hour": last_ats.rem_hour,
                    "rem_min": last_ats.rem_min,
                    "rem_sec": last_ats.rem_sec,
                    "auto_mode": last_ats.auto_mode,
                    "emergency": last_ats.emergency,
                }
        else:
            last_legacy = (
                db.query(data_table)
                .filter(data_table.dev_id == d.dev_id)
                .order_by(data_table.timestamp.desc())
                .first()
            )
            if last_legacy and last_legacy.payload:
                latest_reading = last_legacy.payload
            else:
                last_ts = (
                    db.query(temperature_data)
                    .filter(temperature_data.dev_id == d.dev_id)
                    .order_by(temperature_data.timestamp.desc())
                    .first()
                )
                if last_ts:
                    latest_reading = {
                        "timestamp": last_ts.timestamp.isoformat() if last_ts.timestamp else None,
                        "temp": last_ts.temp,
                        "humid": last_ts.humid,
                    }
                else:
                    last_ats = (
                        db.query(ats_data)
                        .filter(ats_data.dev_id == d.dev_id)
                        .order_by(ats_data.timestamp.desc())
                        .first()
                    )
                    if last_ats:
                        latest_reading = {
                            "timestamp": last_ats.timestamp.isoformat() if last_ats.timestamp else None,
                            "state": last_ats.state,
                            "pln": last_ats.pln,
                            "genset": last_ats.genset,
                            "aki": last_ats.aki,
                            "rem_hour": last_ats.rem_hour,
                            "rem_min": last_ats.rem_min,
                            "rem_sec": last_ats.rem_sec,
                            "auto_mode": last_ats.auto_mode,
                            "emergency": last_ats.emergency,
                        }

        marker_list.append(
            RoomMapMarker(
                dev_id=d.dev_id,
                dev_name=d.dev_name,
                dev_type=d.dev_type,
                marker_x=d.marker_x,
                marker_y=d.marker_y,
                is_active=d.is_active,
                status=status_str,
                latest_reading=latest_reading
            )
        )

    return RoomMapResponse(
        room_id=room.id,
        room_name=room.name,
        has_image=has_image,
        floor_plan_url=floor_plan_url,
        devices=marker_list
    )



# ==========================================
# GATEWAY - ROOM ASSOCIATION (Milestone 2)
# ==========================================

@api.post("/api/gateways/{hub_id}/room")
@limiter.limit("30/minute")
def assign_gateway_room(
    request: Request,
    hub_id: str,
    payload: GatewayRoomAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin associates a gateway with a room."""
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway '{hub_id}' not found"
        )

    room = db.get(rooms, payload.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{payload.room_id}' not found"
        )

    room.hub_id = hub.hub_id
    hub.room = room.name
    db.commit()
    return {"status": "assigned", "hub_id": hub_id, "room_id": payload.room_id}


# ==========================================
# DEVICE PAIRING & UNPAIRING (Milestone 2)
# ==========================================

@api.post("/api/devices/{dev_id}/pair", response_model=DeviceResponse)
@limiter.limit("30/minute")
def pair_device(
    request: Request,
    dev_id: str,
    payload: DevicePairRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin pairs a device: sets name, room, marker position, thresholds, and activates device."""
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found"
        )

    room = db.get(rooms, payload.room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{payload.room_id}' not found"
        )

    device.dev_name = payload.dev_name.strip()
    device.room_id = payload.room_id
    device.marker_x = payload.marker_x
    device.marker_y = payload.marker_y
    device.is_active = True

    # Configure thresholds if provided
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
                debounce_seconds=payload.debounce_seconds if payload.debounce_seconds is not None else 60
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
            debounce_seconds=device.threshold_config.debounce_seconds
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
        threshold_config=thresh_schema
    )


@api.post("/api/devices/{dev_id}/unpair")
@limiter.limit("30/minute")
def unpair_device(
    request: Request,
    dev_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin unpairs a device: clears room, marker coordinates, deactivates device, preserves historical telemetry."""
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found"
        )

    device.room_id = None
    device.marker_x = None
    device.marker_y = None
    device.is_active = False

    db.commit()
    return {"status": "unpaired", "dev_id": dev_id, "is_active": False}


# ==========================================
# DEVICE THRESHOLDS MANAGEMENT (Milestone 4)
# ==========================================

@api.put("/api/devices/{dev_id}/thresholds", response_model=ThresholdConfigSchema)
@limiter.limit("30/minute")
def update_device_thresholds(
    request: Request,
    dev_id: str,
    payload: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5 Milestone 4] Admin sets warning, critical, hysteresis, and debounce thresholds for a device."""
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{dev_id}' not found"
        )

    if payload.warning > payload.critical:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Warning threshold cannot exceed critical threshold"
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
            debounce_seconds=payload.debounce_seconds
        )
        db.add(thresh)

    db.commit()
    db.refresh(thresh)

    return ThresholdConfigSchema(
        warning=thresh.warning,
        critical=thresh.critical,
        hysteresis=thresh.hysteresis,
        debounce_seconds=thresh.debounce_seconds
    )


@api.get("/api/devices/{dev_id}/history", response_model=DeviceHistoryResponse)
@limiter.limit("60/minute")
def get_device_history(
    request: Request,
    dev_id: str,
    range: str = Query("24h"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[V5] Retrieve historical telemetry time-series points for a device."""
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    valid_ranges = {"6h", "24h", "7d", "30d", "all"}
    if range not in valid_ranges:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid range '{range}'. Valid options: 6h, 24h, 7d, 30d, all"
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

    # Time-bucket downsampling for dense windows: high-rate devices (e.g. ATS
    # at ~1.5 Hz) blow past any fixed row limit in minutes, so average into
    # ~1000 buckets across the requested window instead of truncating.
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
                        humid=r.humid
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
                        humid=r.humid
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
                        state=r.state
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
                        state=r.state
                    )
                )

    return DeviceHistoryResponse(
        dev_id=device.dev_id,
        dev_type=device.dev_type or "",
        range=range,
        total_points=len(points),
        points=points
    )


# ==========================================
# ENDPOINTS HUB IOT & DEVICE QUERY (V5)
# ==========================================

@api.get("/api/devices")
@limiter.limit("60/minute")
def get_devices(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    x_hub_id: Optional[str] = Header(None, alias="X-Hub-ID"),
    x_hub_key: Optional[str] = Header(None, alias="X-Hub-Key"),
    db: Session = Depends(get_db)
):
    """
    [V5]
    1. If authenticated via Hub headers (X-Hub-ID, X-Hub-Key):
       Returns whitelist of active devices for that hub.
    2. If authenticated via User session (Cookie session_id):
       Supports filtering by status ('pending', 'active', 'all').
    """
    # 1. Edge Hub authentication path
    if x_hub_id is not None or x_hub_key is not None:
        if not x_hub_id or not x_hub_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub ID dan Key harus disertakan!"
            )
        registered_hub = db.get(hub_table, x_hub_id)
        if not registered_hub or not registered_hub.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!"
            )
        registered_hub_key = registered_hub.hub_key or ""
        if not secrets.compare_digest(registered_hub_key, x_hub_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: API Key Hub tidak cocok!"
            )

        # [V5 PRESENCE] Perbarui heartbeat terakhir Hub pada whitelist sync berhasil
        registered_hub.last_seen = datetime.now(UTC)
        db.commit()

        devices = db.query(dev_table).filter(
            dev_table.is_active == True,
            dev_table.hub_id == registered_hub.hub_id
        ).all()

        return [
            {
                "DEV_ID": d.dev_id,
                "DEV_NAME": d.dev_name,
                "DEV_TYPE": d.dev_type,
                "HUB_NAME": d.hub_id
            }
            for d in devices
        ]

    # 2. User session authentication path
    user = get_current_user(request, db)

    # Auto-prune unapproved pending devices that haven't transmitted in > 25 seconds
    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=25)
    stale_pending = (
        db.query(dev_table)
        .filter(
            dev_table.is_active == False,
            dev_table.room_id.is_(None),
            dev_table.created_at < cutoff
        )
        .all()
    )
    if stale_pending:
        for st in stale_pending:
            db.delete(st)
        db.commit()

    # Online / Offline state tracking & alert generation for paired active devices
    active_devices = db.query(dev_table).filter(dev_table.is_active == True).all()
    has_state_changes = False
    for d in active_devices:
        last_seen_dt = None
        if d.last_seen:
            last_seen_dt = d.last_seen if d.last_seen.tzinfo is not None else d.last_seen.replace(tzinfo=UTC)
        is_online = bool(last_seen_dt and last_seen_dt >= cutoff)

        if not is_online and d.last_status == "online":
            d.last_status = "offline"
            has_state_changes = True
            # Create open DEVICE_OFFLINE alert if none exists
            open_alert = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == d.dev_id,
                    event_log.alarm == "DEVICE_OFFLINE",
                    event_log.resolved_at.is_(None)
                )
                .first()
            )
            if not open_alert:
                dev_label = d.dev_name or d.dev_id
                room_obj = db.get(rooms, d.room_id) if d.room_id else None
                room_name = room_obj.name if room_obj else "Unassigned"
                off_alert = event_log(
                    event_id=uuid.uuid4().hex,
                    alarm="DEVICE_OFFLINE",
                    timestamp=now_utc,
                    message=f"Device '{dev_label}' ({d.dev_id}) in '{room_name}' went OFFLINE (No signal for > 25s).",
                    dev_id=d.dev_id,
                    room_id=d.room_id,
                    metric="connectivity",
                    severity="warning",
                    value=0.0,
                    threshold=1.0,
                    resolved_at=None
                )
                db.add(off_alert)
        elif is_online and d.last_status != "online":
            d.last_status = "online"
            has_state_changes = True

    if has_state_changes:
        db.commit()

    query = db.query(dev_table)
    if status_filter == "pending":
        query = query.filter(dev_table.is_active == False)
    elif status_filter == "active":
        query = query.filter(dev_table.is_active == True)
    elif status_filter == "all" or status_filter is None:
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter. Use 'pending', 'active', or 'all'."
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
                debounce_seconds=d.threshold_config.debounce_seconds
            )
        
        # Calculate dynamic status
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
                threshold_config=thresh_schema
            )
        )
    return results


@api.post("/api/iot/unapproved")
@limiter.limit("60/minute")
def receive_unapproved_alert(
    request: Request,
    payload: UnapprovedDeviceAlert,
    hub: hub_table = Depends(verify_hub_identity), # Verifikasi Hub Aktif & Key
    db: Session = Depends(get_db)
):
    """[V5] Menerima laporan MAC asing yang diblokir di Edge Raspberry Pi."""
    try:
        exist = db.get(dev_table, payload.DEV_ID)
        now_utc = datetime.now(UTC)
        if exist is None:
            new_pending_device = dev_table(
                dev_id=payload.DEV_ID,
                dev_name=payload.DEV_NAME,
                dev_type=payload.DEV_TYPE,
                hub_id=hub.hub_id,
                is_active=False,
                created_at=now_utc
            )
            db.add(new_pending_device)
            db.commit()
            return {"status": "registered_as_pending"}
        else:
            if not exist.is_active and exist.room_id is None:
                exist.created_at = now_utc
                db.commit()
            return {"status": "already_exists"}
    except Exception as e:
        logging.exception("Exception in receive_unapproved_alert")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ==========================================
# INGEST THRESHOLD EVALUATION ENGINE (Milestone 4)
# ==========================================

def evaluate_device_thresholds(
    db: Session,
    dev: dev_table,
    payload: dict,
    timestamp: datetime
) -> None:
    """
    [V5 Milestone 4] Synchronously evaluates threshold rules for incoming telemetry.
    Supports temperature threshold evaluation with debouncing and hysteresis recovery,
    and ATS emergency alert evaluation.
    """
    now_ts = timestamp or datetime.now(UTC)

    # 1. Temperature Evaluation (TS, AC, or any device reporting TEMP)
    if "TEMP" in payload and payload["TEMP"] is not None:
        try:
            temp = float(payload["TEMP"])
        except (ValueError, TypeError):
            temp = None

        if temp is not None:
            # Fetch device threshold config or fallback to defaults
            thresh = db.get(device_threshold_config, dev.dev_id)
            if thresh:
                warning = float(thresh.warning)
                critical = float(thresh.critical)
                hysteresis = float(thresh.hysteresis) if thresh.hysteresis is not None else 0.5
                debounce_seconds = int(thresh.debounce_seconds) if thresh.debounce_seconds is not None else 60
            else:
                warning = 28.0
                critical = 32.0
                hysteresis = 0.5
                debounce_seconds = 60

            # Check breach severity
            severity = None
            threshold_val = None
            if temp >= critical:
                severity = "critical"
                threshold_val = critical
            elif temp >= warning:
                severity = "warning"
                threshold_val = warning

            if severity is not None:
                recent_alert = (
                    db.query(event_log)
                    .filter(
                        event_log.dev_id == dev.dev_id,
                        event_log.metric == "temperature"
                    )
                    .order_by(event_log.timestamp.desc())
                    .first()
                )

                suppress = False
                if recent_alert and recent_alert.timestamp:
                    t_recent = recent_alert.timestamp
                    t_curr = now_ts
                    if t_curr.tzinfo is not None and t_recent.tzinfo is None:
                        t_recent = t_recent.replace(tzinfo=UTC)
                    elif t_curr.tzinfo is None and t_recent.tzinfo is not None:
                        t_curr = t_curr.replace(tzinfo=UTC)

                    elapsed = abs((t_curr - t_recent).total_seconds())
                    if elapsed < debounce_seconds:
                        if recent_alert.severity == severity:
                            suppress = True
                        elif recent_alert.severity == "critical" and severity == "warning":
                            suppress = True

                if not suppress:
                    alarm_code = f"TEMP_{severity.upper()}"
                    dev_label = dev.dev_name or dev.dev_id
                    message = f"Device {dev_label} temperature {temp:.1f}°C exceeded {severity} threshold ({threshold_val:.1f}°C)"
                    new_alert = event_log(
                        event_id=uuid.uuid4().hex,
                        alarm=alarm_code,
                        timestamp=now_ts,
                        message=message,
                        dev_id=dev.dev_id,
                        room_id=dev.room_id,
                        metric="temperature",
                        severity=severity,
                        value=temp,
                        threshold=threshold_val,
                        resolved_at=None
                    )
                    db.add(new_alert)

            # Hysteresis Recovery:
            # If TEMP < (warning - hysteresis), mark open temperature alerts resolved
            if temp < (warning - hysteresis):
                open_alerts = (
                    db.query(event_log)
                    .filter(
                        event_log.dev_id == dev.dev_id,
                        event_log.metric == "temperature",
                        event_log.resolved_at.is_(None)
                    )
                    .all()
                )
                for alert in open_alerts:
                    alert.resolved_at = now_ts

    # 2. ATS Emergency Evaluation
    if "EMERGENCY" in payload and payload["EMERGENCY"] is not None:
        is_emergency = bool(payload["EMERGENCY"])
        if is_emergency:
            thresh = db.get(device_threshold_config, dev.dev_id)
            debounce_seconds = int(thresh.debounce_seconds) if thresh and thresh.debounce_seconds is not None else 60

            recent_alert = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == dev.dev_id,
                    event_log.metric == "emergency"
                )
                .order_by(event_log.timestamp.desc())
                .first()
            )

            suppress = False
            if recent_alert and recent_alert.timestamp:
                t_recent = recent_alert.timestamp
                t_curr = now_ts
                if t_curr.tzinfo is not None and t_recent.tzinfo is None:
                    t_recent = t_recent.replace(tzinfo=UTC)
                elif t_curr.tzinfo is None and t_recent.tzinfo is not None:
                    t_curr = t_curr.replace(tzinfo=UTC)

                elapsed = abs((t_curr - t_recent).total_seconds())
                if elapsed < debounce_seconds and recent_alert.severity == "critical":
                    suppress = True

            if not suppress:
                dev_label = dev.dev_name or dev.dev_id
                new_alert = event_log(
                    event_id=uuid.uuid4().hex,
                    alarm="ATS_EMERGENCY",
                    timestamp=now_ts,
                    message=f"Device {dev_label} reported EMERGENCY state",
                    dev_id=dev.dev_id,
                    room_id=dev.room_id,
                    metric="emergency",
                    severity="critical",
                    value=1.0,
                    threshold=1.0,
                    resolved_at=None
                )
                db.add(new_alert)
        else:
            # Emergency cleared -> resolve open emergency alerts
            open_alerts = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == dev.dev_id,
                    event_log.metric == "emergency",
                    event_log.resolved_at.is_(None)
                )
                .all()
            )
            for alert in open_alerts:
                alert.resolved_at = now_ts


@api.post("/api/iot")
@limiter.limit("120/minute")
def receive_iot(
    request: Request,
    device: IotPayload,
    hub: hub_table = Depends(verify_hub_identity), # Verifikasi Hub Aktif & Key
    db: Session = Depends(get_db)
):
    """[V5] Menerima telemetri terverifikasi dari Edge Hub."""
    try:
        registered_device = db.get(dev_table, device.DEV_ID)
        if not registered_device or not registered_device.is_active:
            raise HTTPException(status_code=403, detail="Device not authorized")

        now_utc = datetime.now(UTC)
        registered_device.last_seen = now_utc
        was_offline = registered_device.last_status == "offline"
        registered_device.last_status = "online"

        if was_offline:
            open_offline_alerts = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == registered_device.dev_id,
                    event_log.alarm == "DEVICE_OFFLINE",
                    event_log.resolved_at.is_(None)
                )
                .all()
            )
            if open_offline_alerts:
                for alert in open_offline_alerts:
                    alert.resolved_at = now_utc

                dev_label = registered_device.dev_name or registered_device.dev_id
                room_obj = db.get(rooms, registered_device.room_id) if registered_device.room_id else None
                room_name = room_obj.name if room_obj else "Unassigned"
                online_event = event_log(
                    event_id=uuid.uuid4().hex,
                    alarm="DEVICE_ONLINE",
                    timestamp=now_utc,
                    message=f"Device '{dev_label}' ({registered_device.dev_id}) in '{room_name}' is back ONLINE.",
                    dev_id=registered_device.dev_id,
                    room_id=registered_device.room_id,
                    metric="connectivity",
                    severity="info",
                    value=1.0,
                    threshold=1.0,
                    resolved_at=now_utc
                )
                db.add(online_event)

        if isinstance(device, TSData):
            new_data = temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                timestamp=now_utc,
                temp=device.TEMP,
                humid=device.HUMID
            )
            db.add(new_data)
        elif isinstance(device, ATSData):
            new_data = ats_data(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                timestamp=now_utc,
                state=device.STATE,
                pln=device.PLN,
                genset=device.GENSET,
                aki=device.AKI,
                rem_hour=device.REM_HOUR,
                rem_min=device.REM_MIN,
                rem_sec=device.REM_SEC,
                auto_mode=device.AUTO_MODE,
                emergency=device.EMERGENCY
            )
            db.add(new_data)
        else:
            new_data = data_table(
                data_id=str(uuid.uuid4()),
                dev_id=device.DEV_ID,
                dev_name=device.DEV_NAME,
                timestamp=now_utc,
                payload=device.model_dump(mode="json")
            )
            db.add(new_data)

            # If payload contains TEMP / HUMID (e.g. ACData, ACCData), also store in temperature_data for time-series charts
            payload_dict = device.model_dump(mode="json")
            if "TEMP" in payload_dict and payload_dict["TEMP"] is not None:
                temp_val = float(payload_dict["TEMP"])
                humid_val = float(payload_dict["HUMID"]) if "HUMID" in payload_dict and payload_dict["HUMID"] is not None else None
                temp_record = temperature_data(
                    data_id=str(uuid.uuid4()),
                    dev_id=device.DEV_ID,
                    timestamp=now_utc,
                    temp=temp_val,
                    humid=humid_val
                )
                db.add(temp_record)

        # [Milestone 4] Threshold Evaluation
        payload_dict = device.model_dump(mode="json")
        evaluate_device_thresholds(db=db, dev=registered_device, payload=payload_dict, timestamp=now_utc)

        db.commit()
        return {"status": "received"}

    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Exception in receive_iot")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record data")


# ==========================================
# ALERTS QUERY ENDPOINTS (Milestone 4)
# ==========================================

def parse_datetime_param(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    val_str = str(val).strip()
    try:
        # Handle trailing Z or z
        if val_str.endswith("Z") or val_str.endswith("z"):
            val_str = val_str[:-1] + "+00:00"
        # If space was decoded from '+' in query string for timezone offset, e.g. "2026-08-17T10:00:00 00:00"
        elif " " in val_str and ("+" not in val_str and "-" not in val_str[10:]):
            parts = val_str.rsplit(" ", 1)
            if len(parts) == 2 and (":" in parts[1] or len(parts[1]) in (2, 4, 5)):
                val_str = f"{parts[0]}+{parts[1]}"
        return datetime.fromisoformat(val_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime format: '{val}'. Expected ISO format (e.g. YYYY-MM-DDTHH:MM:SSZ)."
        )


@api.get("/api/alerts", response_model=AlertListResponse)
@limiter.limit("60/minute")
def get_alerts(
    request: Request,
    rooms_param: Optional[list[str]] = Query(None, alias="rooms"),
    room_param: Optional[str] = Query(None, alias="room"),
    devices_param: Optional[list[str]] = Query(None, alias="devices"),
    device_param: Optional[str] = Query(None, alias="device"),
    severity: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [V5 Milestone 4] List alerts with filtering by rooms, devices, severity, status, and time range.
    """
    query = (
        db.query(
            event_log,
            dev_table.dev_name.label("device_name"),
            rooms.name.label("room_name")
        )
        .outerjoin(dev_table, event_log.dev_id == dev_table.dev_id)
        .outerjoin(rooms, event_log.room_id == rooms.id)
    )

    # 1. Filter by rooms
    parsed_rooms = []
    if rooms_param:
        for r in rooms_param:
            parsed_rooms.extend([x.strip() for x in r.split(",") if x.strip()])
    if room_param:
        parsed_rooms.extend([x.strip() for x in room_param.split(",") if x.strip()])
    if parsed_rooms:
        query = query.filter(event_log.room_id.in_(parsed_rooms))

    # 2. Filter by devices
    parsed_devices = []
    if devices_param:
        for d in devices_param:
            parsed_devices.extend([x.strip() for x in d.split(",") if x.strip()])
    if device_param:
        parsed_devices.extend([x.strip() for x in device_param.split(",") if x.strip()])
    if parsed_devices:
        query = query.filter(event_log.dev_id.in_(parsed_devices))

    # 3. Filter by severity
    if severity:
        sev = severity.strip().lower()
        if sev in ("warning", "critical"):
            query = query.filter(event_log.severity == sev)
        elif sev == "all":
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid severity filter. Use 'warning', 'critical', or 'all'."
            )

    # 4. Filter by status
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
                detail="Invalid status filter. Use 'open', 'resolved', or 'all'."
            )

    # 5. Filter by time range
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
                message=ev.message
            )
        )

    return AlertListResponse(total=total, alerts=alert_list)


@api.post("/api/devices/{dev_id}/command")
@limiter.limit("30/minute")
def send_device_command(
    request: Request,
    dev_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[V5] Kirim command ke perangkat IoT dengan validasi peran (RBAC)."""
    # Check roles based on action
    is_reset = body.get("reset") is not None
    if is_reset:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reset action requires admin role"
            )
    else:
        if current_user.role not in ["admin", "operator"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action requires admin or operator role"
            )

    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        if device.dev_type in ("AC", "ACC") or "target" in body or "action" in body:
            validated_command = ACCommand.model_validate(body)
        else:
            validated_command = ATSCommand.model_validate(body, context={"db": db, "dev_id": dev_id})
    except ValidationError as err:
        from fastapi.exceptions import RequestValidationError
        raise RequestValidationError(err.errors())

    new_cmd = pending_commands(
        command_id=str(uuid.uuid4()),
        dev_id=dev_id,
        hub_id=device.hub_id,
        payload=validated_command.model_dump(mode="json"),
        status="pending"
    )
    db.add(new_cmd)
    db.commit()
    return {"status": "queued", "command_id": new_cmd.command_id}


@api.get("/api/hub/commands")
@limiter.limit("30/minute")
def get_pending_commands(
    request: Request,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db)
):
    """[V5] Hub mengambil command pending untuk semua perangkat miliknya."""
    cmds = db.query(pending_commands).filter(
        pending_commands.hub_id == hub.hub_id,
        pending_commands.status == "pending"
    ).all()

    return [
        {
            "command_id": cmd.command_id,
            "dev_id": cmd.dev_id,
            "payload": cmd.payload,
            "status": cmd.status,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None
        }
        for cmd in cmds
    ]


@api.post("/api/hub/commands/{command_id}/delivered")
@limiter.limit("30/minute")
def mark_command_delivered(
    request: Request,
    command_id: str,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db)
):
    """[V5] Hub menandai command telah berhasil tersampaikan."""
    cmd = db.get(pending_commands, command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    if cmd.hub_id != hub.hub_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this command")

    cmd.status = "delivered"
    cmd.delivered_at = datetime.now(UTC)
    db.commit()
    return {"status": "marked_delivered", "command_id": command_id}


# ==========================================
# HUB ENTITIES & PAIRING API (V5)
# ==========================================

HUB_ONLINE_WINDOW_SECONDS = 25


@api.get("/api/hubs", response_model=list[HubResponse])
@limiter.limit("60/minute")
def list_hubs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """[V5] Menampilkan daftar semua Hub beserta agregasi perangkat dan status kehadiran (online/offline)."""
    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=HUB_ONLINE_WINDOW_SECONDS)

    all_devices = db.query(dev_table).all()
    devices_by_hub: dict[str, list] = {}
    for d in all_devices:
        devices_by_hub.setdefault(d.hub_id, []).append(d)

    all_hubs = db.query(hub_table).all()
    results = []
    for h in all_hubs:
        h_seen = h.last_seen if (h.last_seen and h.last_seen.tzinfo is not None) else (h.last_seen.replace(tzinfo=UTC) if h.last_seen else None)
        hub_status = "online" if (h_seen and h_seen >= cutoff) else "offline"

        hub_devices = devices_by_hub.get(h.hub_id, [])
        results.append(
            HubResponse(
                hub_id=h.hub_id,
                hub_name=h.hub_name,
                room=h.room,
                status=hub_status,
                last_seen=h.last_seen,
                device_count=len(hub_devices),
                devices=[
                    HubDeviceSummary(
                        dev_id=d.dev_id,
                        dev_name=d.dev_name,
                        dev_type=d.dev_type,
                        last_seen=d.last_seen
                    )
                    for d in hub_devices
                ]
            )
        )
    return results


@api.post("/api/hubs/pair")
@limiter.limit("10/minute")
def pair_hub(
    request: Request,
    payload: HubPairRequest,
    x_hub_key: str = Header(..., alias="X-Hub-Key"),
    db: Session = Depends(get_db)
):
    """
    [V5] Bootstrap pairing Hub Edge:
    1. Hub terdaftar & aktif  -> verifikasi X-Hub-Key tersimpan, perbarui kehadiran, status 'paired'.
    2. Hub belum terdaftar    -> butuh HUB_BOOTSTRAP_KEY dari env (provisioning out-of-band);
                                 baris dibuat dengan is_active=False menunggu persetujuan admin (202).
    Endpoint ini bootstrap-only dan hanya aman di jaringan tepercaya saat provisi awal.
    """
    existing = db.get(hub_table, payload.hub_id)
    now_utc = datetime.now(UTC)

    # 1. Hub terdaftar & aktif: alur pairing normal
    if existing and existing.is_active:
        stored_key = existing.hub_key or ""
        if not secrets.compare_digest(stored_key, x_hub_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akses Ditolak: API Key Hub tidak cocok!"
            )
        existing.last_seen = now_utc
        existing.status = "online"
        db.commit()
        return {"status": "paired", "hub_id": existing.hub_id}

    # 2. Hub belum terdaftar / non-aktif: wajib cocok dengan kunci bootstrap yang di-provision via env
    bootstrap_key = os.getenv("HUB_BOOTSTRAP_KEY", "")
    if not bootstrap_key or not secrets.compare_digest(bootstrap_key, x_hub_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: Hub tidak terdaftar atau API Key bootstrap tidak cocok!"
        )

    if not existing:
        clean_name = payload.hub_name.strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="HUB_NAME tidak boleh kosong!"
            )
        new_hub = hub_table(
            hub_id=payload.hub_id,
            hub_name=clean_name,
            hub_key=x_hub_key,
            is_active=False,
            status="offline",
            created_at=now_utc
        )
        db.add(new_hub)
        db.commit()

    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "pending_approval", "hub_id": payload.hub_id})


@api.post("/api/hubs/{hub_id}/approve")
@limiter.limit("30/minute")
def approve_hub(
    request: Request,
    hub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Admin menyetujui Hub pending agar aktif."""
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub tidak ditemukan")

    hub.is_active = True
    db.commit()
    return {"status": "approved", "hub_id": hub_id}


@api.post("/api/hubs/{hub_id}/revoke")
@limiter.limit("30/minute")
def revoke_hub(
    request: Request,
    hub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """[V5] Mencabut akses Hub (non-aktif); verify_hub_identity akan menolak Hub ini."""
    hub = db.get(hub_table, hub_id)
    if not hub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub tidak ditemukan")

    hub.is_active = False
    hub.status = "offline"
    db.commit()
    return {"status": "revoked", "hub_id": hub_id}


# ==========================================
# ENDPOINTS AUTHENTICATION
# ==========================================

@api.post("/api/auth/login", response_model=UserResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    payload: UserLoginPayload,
    response: Response,
    db: Session = Depends(get_db)
):
    normalized_username = payload.username.strip().lower()
    now = datetime.now(UTC)

    # 1. Lockout check
    attempt = db.query(LoginAttempt).filter(LoginAttempt.username == normalized_username).first()
    if attempt:
        locked_until = attempt.locked_until
        if locked_until:
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if locked_until > now:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes."
                )

    # 2. Query user
    user = db.query(User).filter(User.username == normalized_username).first()

    # 3. Verify password timing-safely
    password_matched = verify_password_safe(user.password_hash if user else None, payload.password)

    if not user or not password_matched:
        # Increment failed login attempts tracking
        handle_db_lockout(payload.username, db, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # 4. On success: clear lockout database entries
    handle_db_lockout(payload.username, db, success=True)

    # 5. Create session
    session = create_session(db, user.id)

    # 6. Set response cookie (2-hour sliding TTL)
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
        max_age=7200
    )

    return UserResponse(
        username=user.username,
        display_name=user.display_name,
        role=user.role
    )


@api.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(db, session_id)
    response.delete_cookie("session_id", path="/")
    return {"status": "logged_out"}


@api.get("/api/auth/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return UserResponse(
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role
    )