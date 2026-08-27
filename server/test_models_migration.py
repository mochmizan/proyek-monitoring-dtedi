# test_models_migration.py
# Milestone 1: Database Schema & Additive Migrations Verification Tests

import os
import sys
import uuid
import logging
from datetime import datetime, UTC
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

# Set test database URL
TEST_DB_FILE = "./test_milestone1_migration.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"

# Clean old database if exists
if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

import init_sqlv5
from modelsv5 import (
    Base, hub_table, dev_table, data_table, event_log,
    rooms, device_threshold_config,
    Room, DeviceThresholdConfig, EventLog
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(f"sqlite:///{TEST_DB_FILE}", connect_args={"check_same_thread": False})
    yield engine
    engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest.fixture(scope="module")
def session_factory(db_engine):
    return sessionmaker(autoflush=False, autocommit=False, bind=db_engine)


def test_init_db_creates_all_tables(db_engine):
    """Test that init_db() creates all expected tables including rooms and device_threshold_config."""
    # Ensure init_db executes cleanly on target test engine
    init_sqlv5.init_db(db_engine)

    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    
    assert "rooms" in tables, "Table 'rooms' must exist in database"
    assert "device_threshold_config" in tables, "Table 'device_threshold_config' must exist in database"
    assert "dev_table" in tables, "Table 'dev_table' must exist in database"
    assert "hub_table" in tables, "Table 'hub_table' must exist in database"
    assert "event_log" in tables, "Table 'event_log' must exist in database"

    # Verify columns in dev_table
    dev_cols = {col["name"] for col in inspector.get_columns("dev_table")}
    assert "room_id" in dev_cols, "dev_table must have 'room_id' column"
    assert "marker_x" in dev_cols, "dev_table must have 'marker_x' column"
    assert "marker_y" in dev_cols, "dev_table must have 'marker_y' column"

    # Verify columns in event_log
    event_cols = {col["name"] for col in inspector.get_columns("event_log")}
    assert "event_id" in event_cols, "event_log must have 'event_id' column"
    assert "alarm" in event_cols, "event_log must have 'alarm' column"
    assert "message" in event_cols, "event_log must have 'message' column"
    assert "timestamp" in event_cols, "event_log must have 'timestamp' column"
    assert "dev_id" in event_cols, "event_log must have 'dev_id' column"
    assert "room_id" in event_cols, "event_log must have 'room_id' column"
    assert "metric" in event_cols, "event_log must have 'metric' column"
    assert "severity" in event_cols, "event_log must have 'severity' column"
    assert "value" in event_cols, "event_log must have 'value' column"
    assert "threshold" in event_cols, "event_log must have 'threshold' column"
    assert "resolved_at" in event_cols, "event_log must have 'resolved_at' column"


def test_rooms_crud_and_constraints(session_factory):
    """Test CRUD operations and constraints on the rooms model."""
    db = session_factory()
    try:
        # Create a hub first
        hub = hub_table(
            hub_id="HUB_TEST_R1",
            hub_name="Test Hub 1",
            hub_key="test_key_1",
            room="Room 101",
            is_active=True
        )
        db.add(hub)
        db.commit()

        # 1. Create a room
        room1 = rooms(
            id=str(uuid.uuid4()),
            name="Server Room A",
            hub_id="HUB_TEST_R1",
            floor_plan_image_path="/static/floorplans/room_a.png",
            created_at=datetime.now(UTC)
        )
        db.add(room1)
        db.commit()

        # Verify room persisted
        retrieved_room = db.query(rooms).filter(rooms.name == "Server Room A").first()
        assert retrieved_room is not None
        assert retrieved_room.hub_id == "HUB_TEST_R1"
        assert retrieved_room.floor_plan_image_path == "/static/floorplans/room_a.png"
        assert retrieved_room.hub.hub_name == "Test Hub 1"

        # 2. Test unique name constraint
        duplicate_room = rooms(
            id=str(uuid.uuid4()),
            name="Server Room A",  # Duplicate name
            hub_id="HUB_TEST_R1"
        )
        db.add(duplicate_room)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    finally:
        db.close()


def test_dev_table_room_and_markers(session_factory):
    """Test dev_table association with rooms and marker coordinate storage."""
    db = session_factory()
    try:
        # Create a room
        room_id = str(uuid.uuid4())
        room = rooms(
            id=room_id,
            name="Battery Room B",
            hub_id="HUB_TEST_R1"
        )
        db.add(room)
        db.commit()

        # Create a paired device in this room with marker coordinates
        dev1 = dev_table(
            dev_id="DEV_TEMP_B1",
            dev_name="Temp Sensor B1",
            dev_type="TS",
            hub_id="HUB_TEST_R1",
            room_id=room_id,
            marker_x=45.2,
            marker_y=78.9,
            is_active=True
        )
        db.add(dev1)
        db.commit()

        # Query and verify
        queried_dev = db.query(dev_table).filter(dev_table.dev_id == "DEV_TEMP_B1").first()
        assert queried_dev is not None
        assert queried_dev.room_id == room_id
        assert queried_dev.marker_x == 45.2
        assert queried_dev.marker_y == 78.9
        assert queried_dev.room.name == "Battery Room B"

        # Verify reverse relationship (room.devices)
        queried_room = db.query(rooms).filter(rooms.id == room_id).first()
        device_ids = [d.dev_id for d in queried_room.devices]
        assert "DEV_TEMP_B1" in device_ids

    finally:
        db.close()


def test_device_threshold_config_and_cascade(session_factory):
    """Test device_threshold_config model, default values, and cascade delete behavior."""
    db = session_factory()
    try:
        dev_id = "DEV_TEMP_THRESH_01"
        dev = dev_table(
            dev_id=dev_id,
            dev_name="Threshold Test Sensor",
            dev_type="TS",
            hub_id="HUB_TEST_R1",
            is_active=True
        )
        db.add(dev)
        db.commit()

        # Add threshold config with explicit hysteresis and debounce
        config = device_threshold_config(
            dev_id=dev_id,
            warning=28.0,
            critical=35.0,
            hysteresis=1.0,
            debounce_seconds=120
        )
        db.add(config)
        db.commit()

        # Query back via dev_table relationship
        queried_dev = db.query(dev_table).filter(dev_table.dev_id == dev_id).first()
        assert queried_dev.threshold_config is not None
        assert queried_dev.threshold_config.warning == 28.0
        assert queried_dev.threshold_config.critical == 35.0
        assert queried_dev.threshold_config.hysteresis == 1.0
        assert queried_dev.threshold_config.debounce_seconds == 120

        # Test defaults on a second device
        dev_id_2 = "DEV_TEMP_THRESH_02"
        dev2 = dev_table(
            dev_id=dev_id_2,
            dev_name="Threshold Test Sensor 2",
            dev_type="TS",
            hub_id="HUB_TEST_R1",
            is_active=True
        )
        db.add(dev2)
        db.commit()

        config2 = device_threshold_config(
            dev_id=dev_id_2,
            warning=30.0,
            critical=40.0
            # hysteresis and debounce_seconds should take defaults
        )
        db.add(config2)
        db.commit()

        queried_config2 = db.query(device_threshold_config).filter(device_threshold_config.dev_id == dev_id_2).first()
        assert queried_config2.hysteresis == 0.5
        assert queried_config2.debounce_seconds == 60

        # Test cascade delete: deleting device should cascade delete config
        db.delete(queried_dev)
        db.commit()

        deleted_config = db.query(device_threshold_config).filter(device_threshold_config.dev_id == dev_id).first()
        assert deleted_config is None, "Threshold config should be deleted when device is deleted"

    finally:
        db.close()


def test_event_log_extended_schema(session_factory):
    """Test inserting and querying event_log records with both legacy and new alert engine fields."""
    db = session_factory()
    try:
        # 1. Insert alert engine event with new fields
        alert_event_id = str(uuid.uuid4())
        alert_event = event_log(
            event_id=alert_event_id,
            alarm="CRITICAL_TEMP",
            message="Temperature breached critical threshold (41.2C > 40.0C)",
            timestamp=datetime.now(UTC),
            dev_id="DEV_TEMP_B1",
            room_id="ROOM_001",
            metric="TEMP",
            severity="critical",
            value=41.2,
            threshold=40.0,
            resolved_at=None
        )
        db.add(alert_event)
        db.commit()

        # Query and verify
        queried = db.query(event_log).filter(event_log.event_id == alert_event_id).first()
        assert queried is not None
        assert queried.metric == "TEMP"
        assert queried.severity == "critical"
        assert queried.value == 41.2
        assert queried.threshold == 40.0
        assert queried.resolved_at is None

        # Resolve the alert
        resolved_time = datetime.now(UTC)
        queried.resolved_at = resolved_time
        db.commit()

        updated = db.query(event_log).filter(event_log.event_id == alert_event_id).first()
        assert updated.resolved_at is not None

        # 2. Insert legacy event (only alarm, timestamp, message)
        legacy_event_id = str(uuid.uuid4())
        legacy_event = event_log(
            event_id=legacy_event_id,
            alarm="SYSTEM_RESTART",
            message="Gateway restarted",
            timestamp=datetime.now(UTC)
        )
        db.add(legacy_event)
        db.commit()

        queried_legacy = db.query(event_log).filter(event_log.event_id == legacy_event_id).first()
        assert queried_legacy is not None
        assert queried_legacy.alarm == "SYSTEM_RESTART"
        assert queried_legacy.dev_id is None
        assert queried_legacy.metric is None
        assert queried_legacy.severity is None

    finally:
        db.close()


def test_additive_migration_on_legacy_schema(tmp_path):
    """Test additive migration against a legacy database missing new columns."""
    legacy_db_file = str(tmp_path / "legacy_test.db")
    legacy_engine = create_engine(f"sqlite:///{legacy_db_file}")

    with legacy_engine.begin() as conn:
        # Create legacy dev_table (missing room_id, marker_x, marker_y)
        conn.execute(text("""
            CREATE TABLE dev_table (
                dev_id VARCHAR PRIMARY KEY,
                dev_name VARCHAR,
                dev_type VARCHAR,
                hub_id VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP
            );
        """))
        # Create legacy event_log (missing dev_id, room_id, metric, severity, value, threshold, resolved_at)
        conn.execute(text("""
            CREATE TABLE event_log (
                event_id VARCHAR PRIMARY KEY,
                alarm VARCHAR,
                timestamp TIMESTAMP,
                message VARCHAR
            );
        """))
        # Seed legacy data
        conn.execute(text("""
            INSERT INTO dev_table (dev_id, dev_name, dev_type, hub_id, is_active, created_at)
            VALUES ('LEGACY_DEV_01', 'Legacy Device', 'TS', 'HUB_01', 1, :now);
        """), {"now": datetime.now(UTC)})

        conn.execute(text("""
            INSERT INTO event_log (event_id, alarm, timestamp, message)
            VALUES ('LEGACY_EVT_01', 'OLD_ALARM', :now, 'Old message');
        """), {"now": datetime.now(UTC)})

    # Run additive migration on legacy engine
    try:
        init_sqlv5.migrate_additive_columns(legacy_engine)

        # Check migrated columns
        inspector = inspect(legacy_engine)
        dev_cols = {col["name"] for col in inspector.get_columns("dev_table")}
        assert "room_id" in dev_cols
        assert "marker_x" in dev_cols
        assert "marker_y" in dev_cols

        event_cols = {col["name"] for col in inspector.get_columns("event_log")}
        assert "dev_id" in event_cols
        assert "room_id" in event_cols
        assert "metric" in event_cols
        assert "severity" in event_cols
        assert "value" in event_cols
        assert "threshold" in event_cols
        assert "resolved_at" in event_cols

        # Verify old data was preserved
        with legacy_engine.connect() as conn:
            dev_row = conn.execute(text("SELECT dev_id, dev_name, room_id, marker_x FROM dev_table WHERE dev_id = 'LEGACY_DEV_01';")).mappings().first()
            assert dev_row["dev_name"] == "Legacy Device"
            assert dev_row["room_id"] is None
            assert dev_row["marker_x"] is None

            evt_row = conn.execute(text("SELECT event_id, alarm, metric, severity FROM event_log WHERE event_id = 'LEGACY_EVT_01';")).mappings().first()
            assert evt_row["alarm"] == "OLD_ALARM"
            assert evt_row["metric"] is None
            assert evt_row["severity"] is None

    finally:
        legacy_engine.dispose()
