# schemasv5.py 
# Validasi Payload Pydantic HubGate V5
from datetime import datetime
from typing import Annotated, Literal, Union, Optional, Any
from pydantic import BaseModel, Field, model_validator, ValidationInfo


# ==========================================
# MODEL DASAR (BASE SCHEMA)
# ==========================================
class IotDataBase(BaseModel):
    HUB_NAME: str
    DEV_ID: str      # MAC Address Perangkat
    DEV_NAME: str


# ==========================================
# SKEMA PERANGKAT SPESIFIK
# ==========================================
class ATSData(IotDataBase):
    DEV_TYPE: Literal["ATS"]
    STATE: str
    PLN: float
    GENSET: float
    AKI: float
    REM_HOUR: float
    REM_MIN: float
    REM_SEC: float
    AUTO_MODE: bool
    EMERGENCY: bool


class ATSCommand(BaseModel):
    mode: Optional[Literal["auto", "manual"]] = None
    start_genset: Optional[Literal["on", "off"]] = None
    reset: Optional[Literal["rst"]] = None

    @model_validator(mode="after")
    def check_at_least_one(self) -> "ATSCommand":
        if self.mode is None and self.start_genset is None and self.reset is None:
            raise ValueError("At least one of mode, start_genset, or reset must be provided.")
        return self

    @model_validator(mode="after")
    def check_genset_mode(self, info: ValidationInfo) -> "ATSCommand":
        if self.start_genset == "on":
            if self.mode == "manual":
                return self
            context = info.context
            if context and "db" in context and "dev_id" in context:
                db = context["db"]
                dev_id = context["dev_id"]
                
                # Import ORM models locally inside function to avoid circular imports
                from modelsv5 import ats_data, data_table
                
                # Query newly created ats_data table first
                last_ats = (
                    db.query(ats_data)
                    .filter(ats_data.dev_id == dev_id)
                    .order_by(ats_data.timestamp.desc())
                    .first()
                )
                
                is_manual = False
                found_record = False
                
                if last_ats:
                    found_record = True
                    if last_ats.auto_mode is False or (last_ats.state and last_ats.state.lower() == "manual"):
                        is_manual = True
                else:
                    # Fallback to checking legacy data_table JSONB payload
                    last_legacy = (
                        db.query(data_table)
                        .filter(data_table.dev_id == dev_id)
                        .order_by(data_table.timestamp.desc())
                        .first()
                    )
                    if last_legacy and last_legacy.payload:
                        found_record = True
                        payload = last_legacy.payload
                        auto_mode = payload.get("AUTO_MODE")
                        state = payload.get("STATE")
                        if auto_mode is False or (state and str(state).lower() == "manual"):
                            is_manual = True
                
                if not is_manual:
                    raise ValueError("Cannot start genset unless the device's last known mode was 'manual'.")
        return self


class ACCommand(BaseModel):
    target: Literal["AC1", "AC2"]
    action: Literal["ON", "OFF", "SET_TEMP"]
    temp: Optional[int] = Field(None, ge=16, le=30)

    @model_validator(mode="after")
    def validate_temp_if_set_temp(self) -> "ACCommand":
        if self.action == "SET_TEMP" and self.temp is None:
            raise ValueError("Field 'temp' (16-30) is required when action is 'SET_TEMP'.")
        return self


class TSData(IotDataBase):
    DEV_TYPE: Literal["TS"]
    TEMP: float
    HUMID: float


class ACCData(IotDataBase):
    DEV_TYPE: Literal["ACC"]
    IS_AC1_ON: bool
    IS_AC2_ON: bool


class ACData(IotDataBase):
    DEV_TYPE: Literal["AC"]
    AC1_POWER: str
    AC1_TEMP: float
    AC2_POWER: str
    AC2_TEMP: float
    TEMP: float
    HUMID: float

# Contoh: Jika ada jenis IoT baru, tinggal tambahkan class-nya di sini
'''
class PumpData(IotDataBase):
    DEV_TYPE: Literal["PUMP"]
    PRESSURE: float
    FLOW_RATE: float
    IS_PUMP_ON: bool
'''


# ==========================================
# DISCRIMINATED UNION
# ==========================================

# Daftarkan semua skema perangkat di dalam Union ini
IotPayload = Annotated[
    Union[ATSData, TSData, ACCData, ACData], 
    Field(discriminator="DEV_TYPE")
]


# ==========================================
# SKEMA AUXILIARY & ADMIN MANAGEMENT (V5)
# ==========================================

# Skema untuk laporan perangkat asing (Unapproved/Pending)
class UnapprovedDeviceAlert(BaseModel):
    HUB_NAME: str
    DEV_ID: str
    DEV_TYPE: str
    DEV_NAME: str
    status: str = "PENDING_APPROVAL"


# [V5 SECURITY] Skema untuk Pendaftaran Hub Resmi Baru oleh Admin
class HubRegisterPayload(BaseModel):
    HUB_ID: str
    HUB_NAME: str
    HUB_KEY: str


# ==========================================
# SKEMA ROOM & DEVICE PAIRING (Milestone 2)
# ==========================================

class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    hub_id: Optional[str] = None
    floor_plan_image_path: Optional[str] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    hub_id: Optional[str] = None
    floor_plan_image_path: Optional[str] = None


class RoomResponse(BaseModel):
    id: str
    name: str
    hub_id: Optional[str] = None
    floor_plan_image_path: Optional[str] = None
    device_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GatewayRoomAssign(BaseModel):
    room_id: str


class ThresholdConfigSchema(BaseModel):
    warning: float
    critical: float
    hysteresis: float = 0.5
    debounce_seconds: int = 60

    model_config = {"from_attributes": True}


class DevicePairRequest(BaseModel):
    dev_name: str = Field(..., min_length=1, max_length=100)
    room_id: str
    marker_x: Optional[float] = Field(None, ge=0.0, le=100.0)
    marker_y: Optional[float] = Field(None, ge=0.0, le=100.0)
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    hysteresis: Optional[float] = 0.5
    debounce_seconds: Optional[int] = 60


class DeviceResponse(BaseModel):
    dev_id: str
    dev_name: Optional[str] = None
    dev_type: Optional[str] = None
    hub_id: Optional[str] = None
    is_active: bool
    status: str = "offline"
    last_seen: Optional[datetime] = None
    room_id: Optional[str] = None
    marker_x: Optional[float] = None
    marker_y: Optional[float] = None
    created_at: Optional[datetime] = None
    threshold_config: Optional[ThresholdConfigSchema] = None

    model_config = {"from_attributes": True}


DevicePairResponse = DeviceResponse


# ==========================================
# SKEMA FLOOR PLAN & MAP (Milestone 3)
# ==========================================

class RoomMapMarker(BaseModel):
    dev_id: str
    dev_name: Optional[str] = None
    dev_type: Optional[str] = None
    marker_x: Optional[float] = None
    marker_y: Optional[float] = None
    is_active: bool = False
    status: Optional[str] = None
    latest_reading: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class RoomMapResponse(BaseModel):
    room_id: str
    room_name: str
    has_image: bool
    floor_plan_url: Optional[str] = None
    devices: list[RoomMapMarker] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FloorPlanUploadResponse(BaseModel):
    room_id: str
    floor_plan_url: str
    message: str = "Floor plan uploaded successfully"

    model_config = {"from_attributes": True}


# ==========================================
# SKEMA ALERTS & THRESHOLDS (Milestone 4)
# ==========================================

class ThresholdUpdateRequest(BaseModel):
    warning: float
    critical: float
    hysteresis: float = 0.5
    debounce_seconds: int = 60

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    event_id: str
    dev_id: Optional[str] = None
    dev_name: Optional[str] = None
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    metric: Optional[str] = None
    severity: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: datetime
    resolved_at: Optional[datetime] = None
    message: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    total: int
    alerts: list[AlertResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ==========================================
# SKEMA TELEMETRY HISTORY (Real History API)
# ==========================================

class TelemetryHistoryPoint(BaseModel):
    timestamp: datetime
    temp: Optional[float] = None
    humid: Optional[float] = None
    pln: Optional[float] = None
    genset: Optional[float] = None
    aki: Optional[float] = None
    state: Optional[str] = None

    model_config = {"from_attributes": True}


class DeviceHistoryResponse(BaseModel):
    dev_id: str
    dev_type: str
    range: str
    total_points: int
    points: list[TelemetryHistoryPoint] = Field(default_factory=list)

    model_config = {"from_attributes": True}


