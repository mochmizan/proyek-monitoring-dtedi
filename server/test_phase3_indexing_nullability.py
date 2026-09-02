# test_phase3_indexing_nullability.py
# Comprehensive Test Suite for Phase 3: Schema Indexing & Partial Payload Nullability

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects import postgresql, sqlite

# Ensure server path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import (
    Base, hub_table, dev_table, data_table, temperature_data,
    ats_data, pending_commands, User, UserSession, event_log, rooms
)
from schemasv5 import TSData, ACData
from hubgatev5 import api

client = TestClient(api)
api.state.limiter.enabled = False

TEST_HUB_ID = "HUB_TEST_P3"
TEST_HUB_KEY = "secret_key_p3"
TEST_DEV_TS = "DEV_TS_P3_01"
TEST_DEV_AC = "DEV_AC_P3_01"


@pytest.fixture(scope="module", autouse=True)
def setup_phase3_environment():
    """Initializes isolated test entities for Phase 3."""
    db = SessionLocal()
    try:
        # Register or update test hub
        hub = db.get(hub_table, TEST_HUB_ID)
        if not hub:
            hub = hub_table(
                hub_id=TEST_HUB_ID,
                hub_name="Test Hub Phase 3",
                hub_key=TEST_HUB_KEY,
                is_active=True,
            )
            db.add(hub)
        else:
            hub.is_active = True
            hub.hub_key = TEST_HUB_KEY

        # Register TS device
        dev_ts = db.get(dev_table, TEST_DEV_TS)
        if not dev_ts:
            dev_ts = dev_table(
                dev_id=TEST_DEV_TS,
                dev_name="Temp Sensor Phase 3",
                dev_type="TS",
                hub_id=TEST_HUB_ID,
                is_active=True,
            )
            db.add(dev_ts)
        else:
            dev_ts.is_active = True
            dev_ts.hub_id = TEST_HUB_ID

        # Register AC device
        dev_ac = db.get(dev_table, TEST_DEV_AC)
        if not dev_ac:
            dev_ac = dev_table(
                dev_id=TEST_DEV_AC,
                dev_name="AC Controller Phase 3",
                dev_type="AC",
                hub_id=TEST_HUB_ID,
                is_active=True,
            )
            db.add(dev_ac)
        else:
            dev_ac.is_active = True
            dev_ac.hub_id = TEST_HUB_ID

        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Ensure clean telemetry tables before each test execution."""
    db = SessionLocal()
    try:
        db.query(temperature_data).filter(temperature_data.dev_id.in_([TEST_DEV_TS, TEST_DEV_AC])).delete()
        db.query(data_table).filter(data_table.dev_id.in_([TEST_DEV_TS, TEST_DEV_AC])).delete()
        db.commit()
    finally:
        db.close()


# ==============================================================================
# 1. COMPOSITE INDEX VERIFICATION
# ==============================================================================

def test_composite_indexes_on_models():
    """Verify composite indexes are correctly defined in SQLAlchemy __table_args__."""
    event_log_idx = {idx.name for idx in event_log.__table__.indexes}
    assert "ix_event_log_dev_metric_ts" in event_log_idx
    assert "ix_event_log_room_ts" in event_log_idx
    assert "ix_event_log_dev_resolved" in event_log_idx
    assert "ix_event_log_ts_desc" in event_log_idx

    dev_table_idx = {idx.name for idx in dev_table.__table__.indexes}
    assert "ix_dev_table_hub_id" in dev_table_idx
    assert "ix_dev_table_room_id" in dev_table_idx
    assert "ix_dev_table_dev_name" in dev_table_idx

    pending_idx = {idx.name for idx in pending_commands.__table__.indexes}
    assert "ix_pending_commands_hub_status_created" in pending_idx

    data_table_idx = {idx.name for idx in data_table.__table__.indexes}
    assert "ix_data_table_dev_ts_desc" in data_table_idx

    sessions_idx = {idx.name for idx in UserSession.__table__.indexes}
    assert "ix_sessions_user_expires" in sessions_idx


def test_composite_indexes_in_sqlite_database():
    """Verify all 10 composite/lookup indexes actually exist in SQLite database."""
    inspector = inspect(engine)

    expected_indexes = {
        "event_log": [
            "ix_event_log_dev_metric_ts",
            "ix_event_log_room_ts",
            "ix_event_log_dev_resolved",
            "ix_event_log_ts_desc",
        ],
        "dev_table": [
            "ix_dev_table_hub_id",
            "ix_dev_table_room_id",
            "ix_dev_table_dev_name",
        ],
        "pending_commands": [
            "ix_pending_commands_hub_status_created",
        ],
        "data_table": [
            "ix_data_table_dev_ts_desc",
        ],
        "sessions": [
            "ix_sessions_user_expires",
        ],
    }

    for table_name, index_names in expected_indexes.items():
        actual_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        for expected in index_names:
            assert expected in actual_indexes, f"Index '{expected}' missing from table '{table_name}'. Found: {actual_indexes}"


def test_postgresql_ddl_compilation_for_indexes():
    """Verify PostgreSQL dialect generates standard DDL with descending timestamp expressions."""
    pg_dialect = postgresql.dialect()

    all_indexes = list(event_log.__table__.indexes) + list(data_table.__table__.indexes)
    compiled_statements = {}
    for idx in all_indexes:
        compiled_statements[idx.name] = str(CreateIndex(idx).compile(dialect=pg_dialect))

    # Assert descending expressions compile properly
    assert "timestamp DESC" in compiled_statements["ix_event_log_dev_metric_ts"]
    assert "timestamp DESC" in compiled_statements["ix_event_log_room_ts"]
    assert "timestamp DESC" in compiled_statements["ix_event_log_ts_desc"]
    assert "timestamp DESC" in compiled_statements["ix_data_table_dev_ts_desc"]


# ==============================================================================
# 2. PARTIAL PAYLOAD NULLABILITY (CRIT-04)
# ==============================================================================

def test_temperature_data_columns_are_nullable():
    """Verify modelsv5 temperature_data temp and humid are nullable."""
    assert temperature_data.__table__.c.temp.nullable is True
    assert temperature_data.__table__.c.humid.nullable is True

    # Check live SQLite columns
    inspector = inspect(engine)
    cols = {c["name"]: c["nullable"] for c in inspector.get_columns("temperature_data")}
    assert cols["temp"] is True, f"temp column is not nullable: {cols}"
    assert cols["humid"] is True, f"humid column is not nullable: {cols}"


def test_pydantic_tsdata_schema_validation():
    """Verify TSData accepts partial payloads and strictly rejects empty payloads."""
    # TEMP-only
    p1 = TSData(HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="TS1", DEV_TYPE="TS", TEMP=25.4)
    assert p1.TEMP == 25.4
    assert p1.HUMID is None

    # HUMID-only
    p2 = TSData(HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="TS1", DEV_TYPE="TS", HUMID=60.2)
    assert p2.TEMP is None
    assert p2.HUMID == 60.2

    # Both metrics present
    p3 = TSData(HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="TS1", DEV_TYPE="TS", TEMP=24.0, HUMID=50.0)
    assert p3.TEMP == 24.0
    assert p3.HUMID == 50.0

    # Neither metric present -> must raise ValidationError
    with pytest.raises(ValidationError) as exc1:
        TSData(HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="TS1", DEV_TYPE="TS")
    assert "at least one metric" in str(exc1.value).lower()

    # Both explicit None -> must raise ValidationError
    with pytest.raises(ValidationError) as exc2:
        TSData(HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="TS1", DEV_TYPE="TS", TEMP=None, HUMID=None)
    assert "at least one metric" in str(exc2.value).lower()


def test_pydantic_acdata_schema_validation():
    """Verify ACData accepts partial ambient sensor payloads."""
    # TEMP-only
    ac1 = ACData(
        HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="AC1", DEV_TYPE="AC",
        AC1_POWER="ON", AC1_TEMP=24.0, AC2_POWER="OFF", AC2_TEMP=25.0,
        TEMP=26.5
    )
    assert ac1.TEMP == 26.5
    assert ac1.HUMID is None

    # HUMID-only
    ac2 = ACData(
        HUB_NAME="HUB1", DEV_ID="D1", DEV_NAME="AC1", DEV_TYPE="AC",
        AC1_POWER="ON", AC1_TEMP=24.0, AC2_POWER="OFF", AC2_TEMP=25.0,
        HUMID=58.5
    )
    assert ac2.TEMP is None
    assert ac2.HUMID == 58.5


def test_api_partial_payload_ingestion_temp_only():
    """Ingest TS telemetry with only TEMP via POST /api/iot without IntegrityError."""
    headers = {"X-Hub-ID": TEST_HUB_ID, "X-Hub-Key": TEST_HUB_KEY}
    payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
        "TEMP": 23.5,
    }

    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    assert resp.json()["status"] == "received"

    # Verify database persistence
    db = SessionLocal()
    try:
        record = (
            db.query(temperature_data)
            .filter(temperature_data.dev_id == TEST_DEV_TS)
            .order_by(temperature_data.timestamp.desc())
            .first()
        )
        assert record is not None
        assert record.temp == 23.5
        assert record.humid is None
    finally:
        db.close()


def test_api_partial_payload_ingestion_humid_only():
    """Ingest TS telemetry with only HUMID via POST /api/iot without IntegrityError."""
    headers = {"X-Hub-ID": TEST_HUB_ID, "X-Hub-Key": TEST_HUB_KEY}
    payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
        "HUMID": 55.0,
    }

    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    assert resp.json()["status"] == "received"

    # Verify database persistence
    db = SessionLocal()
    try:
        record = (
            db.query(temperature_data)
            .filter(temperature_data.dev_id == TEST_DEV_TS)
            .order_by(temperature_data.timestamp.desc())
            .first()
        )
        assert record is not None
        assert record.temp is None
        assert record.humid == 55.0
    finally:
        db.close()


def test_api_empty_telemetry_payload_rejected():
    """Empty TS telemetry (neither TEMP nor HUMID) must be rejected with 422."""
    headers = {"X-Hub-ID": TEST_HUB_ID, "X-Hub-Key": TEST_HUB_KEY}
    payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
    }

    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 422, f"Expected 422 Unprocessable Entity, got {resp.status_code}"


def test_api_partial_payload_ingestion_ac_degradation():
    """Ingest AC telemetry with degraded sensor (only HUMID present) via fallback branch."""
    headers = {"X-Hub-ID": TEST_HUB_ID, "X-Hub-Key": TEST_HUB_KEY}
    payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_AC,
        "DEV_NAME": "AC Controller Phase 3",
        "DEV_TYPE": "AC",
        "AC1_POWER": "ON",
        "AC1_TEMP": 22.0,
        "AC2_POWER": "OFF",
        "AC2_TEMP": 24.0,
        "HUMID": 62.0,
    }

    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    assert resp.json()["status"] == "received"

    # Verify database persistence
    db = SessionLocal()
    try:
        record = (
            db.query(temperature_data)
            .filter(temperature_data.dev_id == TEST_DEV_AC)
            .order_by(temperature_data.timestamp.desc())
            .first()
        )
        assert record is not None
        assert record.temp is None
        assert record.humid == 62.0
    finally:
        db.close()


# ==============================================================================
# 3. TIMESTAMP PRECISION & SUB-SECOND INTEGRITY
# ==============================================================================

def test_timestamp_subsecond_precision_storage():
    """Verify sub-second (100ms) timestamps retain microsecond precision without collision."""
    db = SessionLocal()
    try:
        t0 = datetime(2026, 9, 2, 14, 0, 0, 0, tzinfo=UTC)
        t_100ms = t0 + timedelta(milliseconds=100)
        t_1sec = t0 + timedelta(seconds=1)

        d1 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=TEST_DEV_TS,
            timestamp=t0,
            temp=20.0,
            humid=50.0,
        )
        d2 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=TEST_DEV_TS,
            timestamp=t_100ms,
            temp=20.1,
            humid=50.1,
        )
        d3 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=TEST_DEV_TS,
            timestamp=t_1sec,
            temp=20.2,
            humid=50.2,
        )

        db.add_all([d1, d2, d3])
        db.commit()

        # Query all records in range
        rows = (
            db.query(temperature_data)
            .filter(
                temperature_data.dev_id == TEST_DEV_TS,
                temperature_data.timestamp >= t0,
                temperature_data.timestamp <= t_1sec,
            )
            .order_by(temperature_data.timestamp.asc())
            .all()
        )

        assert len(rows) == 3, f"Expected 3 rows, found {len(rows)}"

        # Assert chronological ordering and microsecond retention
        assert rows[0].timestamp.microsecond == 0
        assert rows[1].timestamp.microsecond == 100000  # 100ms preserved
        assert rows[2].timestamp.second == 1
        assert rows[2].timestamp.microsecond == 0

        # Assert no collision or deduplication occurred
        data_ids = {r.data_id for r in rows}
        assert len(data_ids) == 3
    finally:
        db.close()


def test_api_subsecond_telemetry_ingestion():
    """Ingest distinct readings 100ms apart via API and verify preservation."""
    headers = {"X-Hub-ID": TEST_HUB_ID, "X-Hub-Key": TEST_HUB_KEY}
    base_epoch = 1788350000.0  # arbitrary epoch

    # Reading 1 at base_epoch
    p1 = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
        "TEMP": 22.1,
        "HUMID": 49.0,
        "HUB_TS": base_epoch,
    }
    # Reading 2 at base_epoch + 100ms
    p2 = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
        "TEMP": 22.2,
        "HUMID": 49.1,
        "HUB_TS": base_epoch + 0.1,
    }
    # Reading 3 at base_epoch + 1.0s
    p3 = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": TEST_DEV_TS,
        "DEV_NAME": "Temp Sensor Phase 3",
        "DEV_TYPE": "TS",
        "TEMP": 22.3,
        "HUMID": 49.2,
        "HUB_TS": base_epoch + 1.0,
    }

    for p in (p1, p2, p3):
        r = client.post("/api/iot", json=p, headers=headers)
        assert r.status_code == 200, f"Failed: {r.text}"

    # Verify both sub-second and 1-second records are in DB
    db = SessionLocal()
    try:
        t_start = datetime.fromtimestamp(base_epoch - 0.05, tz=UTC)
        t_end = datetime.fromtimestamp(base_epoch + 1.05, tz=UTC)
        recs = (
            db.query(temperature_data)
            .filter(
                temperature_data.dev_id == TEST_DEV_TS,
                temperature_data.timestamp >= t_start,
                temperature_data.timestamp <= t_end,
            )
            .order_by(temperature_data.timestamp.asc())
            .all()
        )
        assert len(recs) == 3
        assert recs[0].temp == 22.1
        assert recs[1].temp == 22.2
        assert recs[2].temp == 22.3
    finally:
        db.close()


# ==============================================================================
# 4. ALEMBIC MIGRATION CYCLE (UPGRADE / DOWNGRADE ROUND-TRIP)
# ==============================================================================

def test_alembic_migration_round_trip():
    """Verify Alembic migration c1a8b9f0e2d3 upgrade, downgrade, and re-upgrade."""
    import alembic.config
    import alembic.command

    # Create an isolated SQLite database file for testing migration cycle
    test_mig_db = "test_alembic_cycle.db"
    if os.path.exists(test_mig_db):
        try:
            os.remove(test_mig_db)
        except OSError:
            pass

    test_mig_url = f"sqlite:///{os.path.abspath(test_mig_db)}"
    mig_engine = create_engine(test_mig_url)

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cfg = alembic.config.Config(os.path.join(base_dir, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
        cfg.set_main_option("sqlalchemy.url", test_mig_url)

        # 1. Upgrade from scratch to head (c1a8b9f0e2d3)
        alembic.command.upgrade(cfg, "head")

        inspector = inspect(mig_engine)
        # Check that composite indexes exist after upgrade
        event_idx = {idx["name"] for idx in inspector.get_indexes("event_log")}
        assert "ix_event_log_dev_metric_ts" in event_idx
        assert "ix_event_log_room_ts" in event_idx
        assert "ix_event_log_dev_resolved" in event_idx
        assert "ix_event_log_ts_desc" in event_idx

        # Check nullability
        cols = {c["name"]: c["nullable"] for c in inspector.get_columns("temperature_data")}
        assert cols["temp"] is True
        assert cols["humid"] is True

        # 2. Downgrade to b7c9e2f1a4d8
        alembic.command.downgrade(cfg, "b7c9e2f1a4d8")

        inspector_down = inspect(mig_engine)
        event_idx_down = {idx["name"] for idx in inspector_down.get_indexes("event_log")}
        assert "ix_event_log_dev_metric_ts" not in event_idx_down
        assert "ix_event_log_room_ts" not in event_idx_down
        assert "ix_event_log_dev_resolved" not in event_idx_down
        assert "ix_event_log_ts_desc" not in event_idx_down

        cols_down = {c["name"]: c["nullable"] for c in inspector_down.get_columns("temperature_data")}
        assert cols_down["temp"] is False
        assert cols_down["humid"] is False

        # 3. Re-upgrade to head
        alembic.command.upgrade(cfg, "head")

        inspector_up = inspect(mig_engine)
        event_idx_up = {idx["name"] for idx in inspector_up.get_indexes("event_log")}
        assert "ix_event_log_dev_metric_ts" in event_idx_up
        assert "ix_event_log_room_ts" in event_idx_up

        cols_up = {c["name"]: c["nullable"] for c in inspector_up.get_columns("temperature_data")}
        assert cols_up["temp"] is True
        assert cols_up["humid"] is True

    finally:
        mig_engine.dispose()
        if os.path.exists(test_mig_db):
            try:
                os.remove(test_mig_db)
            except OSError:
                pass
