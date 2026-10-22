# modelsv5.py — Database schema definitions for HubGate V5

import uuid
from datetime import UTC, datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Index, JSON, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from databasev5 import Base

# Column type compatibility helper for SQLite (tests) and PostgreSQL (production)
JSON_TYPE = JSONB().with_variant(JSON, "sqlite")


class hub_table(Base):
    __tablename__ = "hub_table"

    hub_id = Column(String, primary_key=True)
    hub_name = Column(String, nullable=False)
    hub_key = Column(String, nullable=False)
    room = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="offline", nullable=True)

    # Relationships
    devices = relationship("dev_table", back_populates="hub")


class rooms(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    hub_id = Column(String, ForeignKey("hub_table.hub_id"), nullable=True)
    floor_plan_image_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    hub = relationship("hub_table", backref="assigned_rooms")
    devices = relationship("dev_table", back_populates="room")


class dev_table(Base):
    __tablename__ = "dev_table"

    dev_id = Column(String, primary_key=True)
    dev_name = Column(String)
    dev_type = Column(String)
    hub_id = Column(String, ForeignKey("hub_table.hub_id"))
    
    # False = pending (unapproved), True = active (approved)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String, default="offline", nullable=True)

    # Room & Marker Fields (Milestone 1)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=True)
    marker_x = Column(Float, nullable=True)
    marker_y = Column(Float, nullable=True)

    # Relationships
    hub = relationship("hub_table", back_populates="devices")
    room = relationship("rooms", back_populates="devices")
    telemetry_data = relationship("data_table", back_populates="device", cascade="all, delete-orphan")
    temperature_records = relationship("temperature_data", back_populates="device", cascade="all, delete-orphan")
    ats_records = relationship("ats_data", back_populates="device", cascade="all, delete-orphan")
    threshold_config = relationship("device_threshold_config", back_populates="device", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_dev_table_hub_id", "hub_id"),
        Index("ix_dev_table_room_id", "room_id"),
        Index("ix_dev_table_dev_name", "dev_name"),
    )


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

    # Relationship to dev_table
    device = relationship("dev_table", back_populates="telemetry_data")

    __table_args__ = (
        Index("ix_data_table_dev_ts_desc", "dev_id", text("timestamp DESC")),
        UniqueConstraint("dev_id", "timestamp", name="uq_data_dev_timestamp"),
    )


class event_log(Base):
    __tablename__ = "event_log"

    event_id = Column(String, primary_key=True)
    alarm = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    message = Column(String, nullable=True)

    dev_id = Column(String, nullable=True)
    room_id = Column(String, nullable=True)
    metric = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    value = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_event_log_dev_metric_ts", "dev_id", "metric", text("timestamp DESC")),
        Index("ix_event_log_room_ts", "room_id", text("timestamp DESC")),
        Index("ix_event_log_dev_resolved", "dev_id", "resolved_at"),
        Index("ix_event_log_ts_desc", text("timestamp DESC")),
    )


class temperature_data(Base):
    __tablename__ = "temperature_data"

    data_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    temp = Column(Float, nullable=True)
    humid = Column(Float, nullable=True)

    # Relationship to dev_table
    device = relationship("dev_table", back_populates="temperature_records")

    __table_args__ = (
        Index("idx_temp_dev_timestamp", "dev_id", timestamp.desc()),
        UniqueConstraint("dev_id", "timestamp", name="uq_temp_dev_timestamp"),
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

    # Legacy fields
    rem_hour = Column(Float, nullable=True)
    rem_min = Column(Float, nullable=True)
    rem_sec = Column(Float, nullable=True)

    # Parameter baru untuk status ATS v5
    auto_mode = Column(Boolean, nullable=False, default=False)
    emergency = Column(Boolean, nullable=False, default=False)
    pln_relay = Column(Boolean, nullable=False, default=False)
    gen_relay = Column(Boolean, nullable=False, default=False)
    alarm = Column(Boolean, nullable=False, default=False)
    warmup = Column(Boolean, nullable=False, default=False)

    # Relationship to dev_table
    device = relationship("dev_table", back_populates="ats_records")

    __table_args__ = (
        Index("idx_ats_dev_timestamp", "dev_id", text("timestamp DESC")),
        UniqueConstraint("dev_id", "timestamp", name="uq_ats_dev_timestamp"),
    )


class _TemperatureRollup:
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), primary_key=True)
    bucket_start = Column(DateTime(timezone=True), primary_key=True)
    temp_sum = Column(Float, nullable=False, default=0.0)
    temp_count = Column(Integer, nullable=False, default=0)
    temp_avg = Column(Float, nullable=True)
    temp_min = Column(Float, nullable=True)
    temp_max = Column(Float, nullable=True)
    humid_sum = Column(Float, nullable=False, default=0.0)
    humid_count = Column(Integer, nullable=False, default=0)
    humid_avg = Column(Float, nullable=True)
    humid_min = Column(Float, nullable=True)
    humid_max = Column(Float, nullable=True)


class temperature_hourly(_TemperatureRollup, Base):
    __tablename__ = "temperature_hourly"
    __table_args__ = (Index("ix_temperature_hourly_dev_bucket", "dev_id", "bucket_start", unique=True),)


class temperature_daily(_TemperatureRollup, Base):
    __tablename__ = "temperature_daily"
    __table_args__ = (Index("ix_temperature_daily_dev_bucket", "dev_id", "bucket_start", unique=True),)


class temperature_monthly(_TemperatureRollup, Base):
    __tablename__ = "temperature_monthly"
    __table_args__ = (Index("ix_temperature_monthly_dev_bucket", "dev_id", "bucket_start", unique=True),)


class _ATSRollup:
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), primary_key=True)
    bucket_start = Column(DateTime(timezone=True), primary_key=True)
    pln_sum = Column(Float, nullable=False, default=0.0)
    pln_count = Column(Integer, nullable=False, default=0)
    pln_avg = Column(Float, nullable=True)
    pln_min = Column(Float, nullable=True)
    pln_max = Column(Float, nullable=True)
    genset_sum = Column(Float, nullable=False, default=0.0)
    genset_count = Column(Integer, nullable=False, default=0)
    genset_avg = Column(Float, nullable=True)
    genset_min = Column(Float, nullable=True)
    genset_max = Column(Float, nullable=True)
    aki_sum = Column(Float, nullable=False, default=0.0)
    aki_count = Column(Integer, nullable=False, default=0)
    aki_avg = Column(Float, nullable=True)
    aki_min = Column(Float, nullable=True)
    aki_max = Column(Float, nullable=True)
    first_state = Column(String, nullable=True)
    last_state = Column(String, nullable=True)
    first_emergency = Column(Boolean, nullable=True)
    last_emergency = Column(Boolean, nullable=True)
    state_change_count = Column(Integer, nullable=False, default=0)
    emergency_event_count = Column(Integer, nullable=False, default=0)


class ats_hourly(_ATSRollup, Base):
    __tablename__ = "ats_hourly"
    __table_args__ = (Index("ix_ats_hourly_dev_bucket", "dev_id", "bucket_start", unique=True),)


class ats_daily(_ATSRollup, Base):
    __tablename__ = "ats_daily"
    __table_args__ = (Index("ix_ats_daily_dev_bucket", "dev_id", "bucket_start", unique=True),)


class ats_monthly(_ATSRollup, Base):
    __tablename__ = "ats_monthly"
    __table_args__ = (Index("ix_ats_monthly_dev_bucket", "dev_id", "bucket_start", unique=True),)


class pending_commands(Base):
    __tablename__ = "pending_commands"

    command_id = Column(String, primary_key=True)
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    hub_id = Column(String, ForeignKey("hub_table.hub_id", ondelete="CASCADE"), nullable=False)
    payload = Column(JSON_TYPE, nullable=False)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    device = relationship("dev_table", backref="pending_commands")
    hub = relationship("hub_table", backref="pending_commands")

    __table_args__ = (
        Index("ix_pending_commands_hub_status_created", "hub_id", "status", "created_at"),
    )


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
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC), 
        nullable=False
    )
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    # Relationship to User
    user = relationship("User", backref="sessions")

    __table_args__ = (
        Index("ix_sessions_user_expires", "user_id", "expires_at"),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    username = Column(String, primary_key=True, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)


class schedules(Base):
    __tablename__ = "schedules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dev_id = Column(String, ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False)
    hub_id = Column(String, ForeignKey("hub_table.hub_id", ondelete="CASCADE"), nullable=True)
    cron_expr = Column(String(64), nullable=False)
    payload = Column(JSON_TYPE, nullable=False)
    tz = Column(String(32), nullable=False, default="Asia/Jakarta")
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    next_run_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    device = relationship("dev_table", backref="schedules")
    hub = relationship("hub_table", backref="schedules")

    __table_args__ = (
        Index("ix_schedules_enabled_hub", "enabled", "hub_id"),
        Index("ix_schedules_dev", "dev_id"),
    )


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    target_user_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_name = Column(String, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    role = Column(String, nullable=True, index=True)
    activity = Column(JSON_TYPE, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)

    __table_args__ = (
        Index("ix_activity_logs_user_name_created", "user_name", "created_at"),
    )


# Standard PascalCase ORM Model Aliases
Hub = hub_table
Room = rooms
Device = dev_table
TemperatureData = temperature_data
ATSData = ats_data
DataTable = data_table
EventLog = event_log
PendingCommand = pending_commands
DeviceThresholdConfig = device_threshold_config
Schedule = schedules
activity_logs = ActivityLog


