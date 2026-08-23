# modelsv5.py 
# Pendefinisian Skema Database HubGate V5

import uuid
from datetime import UTC, datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Index, JSON, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Import Base dari databasev5 agar terhubung langsung dengan engine & session V5
from databasev5 import Base

# Helper untuk kompatibilitas SQLite (untuk testing) dan PostgreSQL (production)
JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class hub_table(Base):
    __tablename__ = "hub_table"

    hub_id = Column(String, primary_key=True)                   # Contoh: "RASPI_HUB_01"
    hub_name = Column(String, nullable=False)                 # Contoh: "Hub Gedung A"
    hub_key = Column(String, nullable=False)                  # [V5 SECURITY] API Key Rahasia Hub
    room = Column(String, nullable=True)                      # Lokasi/Ruangan Hub
    is_active = Column(Boolean, default=True, nullable=False)   # [V5 SECURITY] Status pendaftaran/blokir Hub
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class rooms(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    hub_id = Column(String, ForeignKey("hub_table.hub_id"), nullable=True)
    floor_plan_image_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relasi
    hub = relationship("hub_table", backref="assigned_rooms")
    devices = relationship("dev_table", back_populates="room")


class dev_table(Base):
    __tablename__ = "dev_table"

    dev_id = Column(String, primary_key=True)                  # MAC Address Perangkat IoT
    dev_name = Column(String)
    dev_type = Column(String)
    hub_id = Column(String, ForeignKey("hub_table.hub_id"))                                  # Identitas Hub Pengelola
    
    # KUNCI UNTUK SYSTEM APPROVAL & WHITELIST
    # False = Pending (Ditolak oleh Hub), True = Active (Diterima oleh Hub)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String, default="offline", nullable=True)

    # Room & Marker Fields (Milestone 1)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=True)
    marker_x = Column(Float, nullable=True)
    marker_y = Column(Float, nullable=True)

    # Relasi ke data_table, rooms, dan device_threshold_config
    telemetry_data = relationship("data_table", back_populates="device", cascade="all, delete-orphan")
    room = relationship("rooms", back_populates="devices")
    threshold_config = relationship("device_threshold_config", back_populates="device", uselist=False, cascade="all, delete-orphan")


class device_threshold_config(Base):
    __tablename__ = "device_threshold_config"

    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), primary_key=True)
    warning = Column(Float, nullable=False)
    critical = Column(Float, nullable=False)
    hysteresis = Column(Float, nullable=False, default=0.5)
    debounce_seconds = Column(Integer, nullable=False, default=60)

    device = relationship("dev_table", back_populates="threshold_config")


class data_table(Base):
    __tablename__ = "data_table"

    data_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"))
    dev_name = Column(String)
    
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    payload = Column(JSON_TYPE)

    # Relasi balik ke dev_table
    device = relationship("dev_table", back_populates="telemetry_data")


class event_log(Base):
    __tablename__ = "event_log"

    event_id = Column(String, primary_key=True)
    alarm = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    message = Column(String, nullable=True)

    # Kolom Alert Engine (Milestone 1)
    dev_id = Column(String, nullable=True)
    room_id = Column(String, nullable=True)
    metric = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class temperature_data(Base):
    __tablename__ = "temperature_data"

    data_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    temp = Column(Float, nullable=False)
    humid = Column(Float, nullable=False)

    __table_args__ = (
        Index("idx_temp_dev_timestamp", "dev_id", timestamp.desc()),
    )


class ats_data(Base):
    __tablename__ = "ats_data"

    data_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    state = Column(String, nullable=False)
    pln = Column(Float, nullable=False)
    genset = Column(Float, nullable=False)
    aki = Column(Float, nullable=False)
    rem_hour = Column(Float, nullable=False)
    rem_min = Column(Float, nullable=False)
    rem_sec = Column(Float, nullable=False)
    auto_mode = Column(Boolean, nullable=False)
    emergency = Column(Boolean, nullable=False)

    __table_args__ = (
        Index("idx_ats_dev_timestamp", "dev_id", timestamp.desc()),
    )


class pending_commands(Base):
    __tablename__ = "pending_commands"

    command_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    hub_id = Column(String, ForeignKey("hub_table.hub_id", ondelete="CASCADE"), nullable=False)
    payload = Column(JSON_TYPE, nullable=False)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin or operator
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    lockout_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class UserSession(Base):
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    username = Column(String, primary_key=True, index=True)  # Normalized
    attempts = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)


# Aliases for consistent naming
Room = rooms
DeviceThresholdConfig = device_threshold_config
EventLog = event_log
