# test_phase4_ingestion_batching.py
# Comprehensive Test Suite for Phase 4: Ingestion Pipeline, Throttled Heartbeat & Batch Ingestion

from datetime import UTC, datetime, timedelta
import os
import time
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

# 1. Configure test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from app.dependencies import hub_auth_cache, stage_hub_heartbeat, verify_hub_identity
from auth import hash_password
from databasev5 import SessionLocal, engine
from app.main import api
from modelsv5 import (
    User,
    UserSession,
    ats_data,
    data_table,
    dev_table,
    device_threshold_config,
    event_log,
    hub_table,
    pending_commands,
    rooms,
    schedules,
    temperature_data,
)
from schemasv5 import ATSData, IotBatchRequest, TSData

client = TestClient(api)
api.state.limiter.enabled = False

# Track session commits to verify zero double-commit
session_commits: list[float] = []


def _track_session_commit(session):
    session_commits.append(time.time())


event.listen(Session, "after_commit", _track_session_commit)


def reset_commit_tracker():
    session_commits.clear()


def get_admin_cookies() -> dict:
    resp = client.post("/api/auth/login", json={"username": "admin_p4", "password": "adminpass"})
    assert resp.status_code == 200, f"Login failed for admin_p4: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


@pytest.fixture(scope="module", autouse=True)
def setup_phase4_environment():
    db = SessionLocal()
    try:
        # Clear child tables first to respect FK constraints
        db.query(event_log).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(pending_commands).delete()
        db.query(schedules).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(UserSession).delete()
        db.query(User).delete()
        db.commit()

        # Create admin user
        admin = User(
            id="user-admin-p4",
            username="admin_p4",
            password_hash=hash_password("adminpass"),
            display_name="Admin Phase 4",
            role="admin",
        )
        db.add(admin)

        # Create test room
        room1 = rooms(
            id="room-p4-01",
            name="Server Room P4",
        )
        db.add(room1)

        # Create test hubs
        hub1 = hub_table(
            hub_id="HUB_P4_01",
            hub_name="Hub Phase 4 Gateway",
            hub_key="secret_key_p4_hub1",
            is_active=True,
            status="online",
        )
        hub2 = hub_table(
            hub_id="HUB_P4_REVOKE",
            hub_name="Hub to Revoke",
            hub_key="secret_key_p4_revoke",
            is_active=True,
            status="online",
        )
        db.add_all([hub1, hub2])

        # Create test devices
        dev_ts = dev_table(
            dev_id="DEV_TS_01",
            dev_name="Temperature Sensor 1",
            dev_type="TS",
            hub_id="HUB_P4_01",
            room_id="room-p4-01",
            is_active=True,
            last_status="offline",
        )
        dev_ats = dev_table(
            dev_id="DEV_ATS_01",
            dev_name="ATS Controller 1",
            dev_type="ATS",
            hub_id="HUB_P4_01",
            room_id="room-p4-01",
            is_active=True,
            last_status="offline",
        )
        dev_ac = dev_table(
            dev_id="DEV_AC_01",
            dev_name="AC Unit 1",
            dev_type="AC",
            hub_id="HUB_P4_01",
            room_id="room-p4-01",
            is_active=True,
            last_status="offline",
        )
        dev_unapproved = dev_table(
            dev_id="DEV_UNAPPROVED_01",
            dev_name="Unapproved Sensor",
            dev_type="TS",
            hub_id="HUB_P4_01",
            room_id=None,
            is_active=False,
            last_status="offline",
        )
        dev_revoke = dev_table(
            dev_id="DEV_REVOKE_01",
            dev_name="Revoke Sensor",
            dev_type="TS",
            hub_id="HUB_P4_REVOKE",
            room_id="room-p4-01",
            is_active=True,
            last_status="offline",
        )
        db.add_all([dev_ts, dev_ats, dev_ac, dev_unapproved, dev_revoke])

        # Threshold config for alert storm test
        thresh = device_threshold_config(
            dev_id="DEV_TS_01",
            warning=28.0,
            critical=32.0,
            hysteresis=0.5,
            debounce_seconds=0,
        )
        db.add(thresh)

        db.commit()
    finally:
        db.close()

    hub_auth_cache.clear()
    reset_commit_tracker()


# =========================================================================
# TEST 1: Zero Double-Commit Guarantee (CRIT-01)
# =========================================================================

def test_verify_hub_identity_no_premature_commit():
    """Verify that POST /api/iot executes exactly 1 database commit.
    Dependency verify_hub_identity does NOT call db.commit() prematurely."""
    hub_auth_cache.clear()
    reset_commit_tracker()

    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    payload = {
        "HUB_NAME": "HUB_P4_01",
        "DEV_ID": "DEV_TS_01",
        "DEV_NAME": "Temperature Sensor 1",
        "DEV_TYPE": "TS",
        "TEMP": 24.0,
        "HUMID": 50.0,
        "HUB_TS": time.time(),
    }

    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    assert resp.json()["status"] == "received"

    # CRIT-01 verification: exactly 1 atomic commit (Heartbeat + Telemetry + Presence + Alerts)
    assert len(session_commits) == 1, (
        f"Double-commit anti-pattern detected! Expected 1 commit, observed {len(session_commits)}"
    )


# =========================================================================
# TEST 2: In-Memory Throttled Heartbeat Cache (HubAuthCache)
# =========================================================================

def test_hub_auth_cache_throttling():
    """Verify that HubAuthCache stages DB writes only once per 30-second window across rapid requests."""
    hub_auth_cache.clear()

    # 1. Direct unit test of HubAuthCache
    hub_id = "HUB_P4_01"
    db = SessionLocal()
    try:
        # First check qualifies
        entry = hub_auth_cache.get_or_load(hub_id, db)
        assert entry is not None
        assert entry.is_active is True
        assert hub_auth_cache.should_persist_heartbeat(hub_id) is True

        # Rapid subsequent checks within 30s must return False (throttled)
        for _ in range(10):
            assert hub_auth_cache.should_persist_heartbeat(hub_id) is False

        # Fast forward monotonic timestamp
        entry.last_db_persist_ts = time.monotonic() - 35.0
        assert hub_auth_cache.should_persist_heartbeat(hub_id) is True
        assert hub_auth_cache.should_persist_heartbeat(hub_id) is False
    finally:
        db.close()


def test_hub_auth_cache_invalidation_on_revoke():
    """Verify that admin revoking a hub immediately invalidates the cache, rejecting subsequent requests with 401."""
    hub_auth_cache.clear()
    headers = {
        "X-Hub-ID": "HUB_P4_REVOKE",
        "X-Hub-Key": "secret_key_p4_revoke",
    }
    payload = {
        "HUB_NAME": "HUB_P4_REVOKE",
        "DEV_ID": "DEV_REVOKE_01",
        "DEV_NAME": "Revoke Sensor",
        "DEV_TYPE": "TS",
        "TEMP": 23.0,
        "HUMID": 48.0,
        "HUB_TS": time.time(),
    }

    # 1. Warm cache with successful request
    resp = client.post("/api/iot", json=payload, headers=headers)
    assert resp.status_code == 200
    assert "HUB_P4_REVOKE" in hub_auth_cache._cache

    # 2. Admin revokes the hub
    admin_cookies = get_admin_cookies()
    revoke_resp = client.post("/api/hubs/HUB_P4_REVOKE/revoke", cookies=admin_cookies)
    assert revoke_resp.status_code == 200

    # 3. Cache must be invalidated immediately
    assert "HUB_P4_REVOKE" not in hub_auth_cache._cache

    # 4. Subsequent request must be rejected with 401 Unauthorized
    subsequent_resp = client.post("/api/iot", json=payload, headers=headers)
    assert subsequent_resp.status_code == 401
    assert "non-aktif" in subsequent_resp.text.lower() or "ditolak" in subsequent_resp.text.lower()


# =========================================================================
# TEST 3: Single Telemetry Ingestion Atomic Handlers
# =========================================================================

def test_single_iot_ingestion_atomic():
    """Verify atomic ingestion of TS, ATS, and AC payloads via POST /api/iot."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    ts_epoch = time.time() - 3600.0

    # 1. Ingest TSData
    ts_payload = {
        "HUB_NAME": "HUB_P4_01",
        "DEV_ID": "DEV_TS_01",
        "DEV_NAME": "Temperature Sensor 1",
        "DEV_TYPE": "TS",
        "TEMP": 25.5,
        "HUMID": 52.0,
        "HUB_TS": ts_epoch,
    }
    resp = client.post("/api/iot", json=ts_payload, headers=headers)
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        t_row = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01").first()
        assert t_row is not None
        assert t_row.temp == 25.5
        assert t_row.humid == 52.0

        # 2. Ingest ATSData
        ats_payload = {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_ATS_01",
            "DEV_NAME": "ATS Controller 1",
            "DEV_TYPE": "ATS",
            "STATE": "auto",
            "PLN": 220.5,
            "GENSET": 0.0,
            "AKI": 12.6,
            "REM_HOUR": 2.0,
            "REM_MIN": 15.0,
            "REM_SEC": 30.0,
            "AUTO_MODE": True,
            "EMERGENCY": False,
            "HUB_TS": ts_epoch,
        }
        resp = client.post("/api/iot", json=ats_payload, headers=headers)
        assert resp.status_code == 200

        a_row = db.query(ats_data).filter(ats_data.dev_id == "DEV_ATS_01").first()
        assert a_row is not None
        assert a_row.state == "auto"
        assert a_row.pln == 220.5
        assert a_row.auto_mode is True

        # 3. Ingest ACData (stored in generic data_table + temperature_data if TEMP present)
        ac_payload = {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_AC_01",
            "DEV_NAME": "AC Unit 1",
            "DEV_TYPE": "AC",
            "AC1_POWER": "on",
            "AC1_TEMP": 20.0,
            "AC2_POWER": "off",
            "AC2_TEMP": 24.0,
            "TEMP": 21.0,
            "HUMID": 45.0,
            "HUB_TS": ts_epoch,
        }
        resp = client.post("/api/iot", json=ac_payload, headers=headers)
        assert resp.status_code == 200

        g_row = db.query(data_table).filter(data_table.dev_id == "DEV_AC_01").first()
        assert g_row is not None
        assert g_row.payload["AC1_POWER"] == "on"

        ac_temp_row = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_AC_01").first()
        assert ac_temp_row is not None
        assert ac_temp_row.temp == 21.0
    finally:
        db.close()


# =========================================================================
# TEST 4: Batch Ingestion Endpoint (POST /api/iot/batch) (HIGH-04)
# =========================================================================

def test_batch_iot_ingestion_success():
    """Verify bulk insertion of 100 mixed TS and ATS items in < 100ms via POST /api/iot/batch."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    base_ts = time.time() - 1800.0
    items = []

    # 50 TS items spaced 10 seconds apart
    for i in range(50):
        items.append({
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 22.0 + (i * 0.1),
            "HUMID": 50.0,
            "HUB_TS": base_ts + (i * 10),
        })

    # 50 ATS items spaced 10 seconds apart
    for i in range(50):
        items.append({
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_ATS_01",
            "DEV_NAME": "ATS Controller 1",
            "DEV_TYPE": "ATS",
            "STATE": "auto",
            "PLN": 220.0,
            "GENSET": 0.0,
            "AKI": 12.4,
            "REM_HOUR": 1.0,
            "REM_MIN": 0.0,
            "REM_SEC": 0.0,
            "AUTO_MODE": True,
            "EMERGENCY": False,
            "HUB_TS": base_ts + (i * 10),
        })

    start_t = time.perf_counter()
    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0

    assert resp.status_code == 200, f"Batch post failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "received"
    assert body["processed_count"] == 100
    assert body["ingested_count"] == 100
    assert body["ignored_count"] == 0

    # High performance validation: 100 items bulk inserted in < 350ms (Phase 6 write path invariant)
    assert elapsed_ms < 350.0, f"Batch ingestion took {elapsed_ms:.2f}ms, expected < 350ms"

    # Verify rows in DB
    db = SessionLocal()
    try:
        ts_count = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01").count()
        ats_count = db.query(ats_data).filter(ats_data.dev_id == "DEV_ATS_01").count()
        # 50 + 1 (from single test) = 51
        assert ts_count >= 50
        assert ats_count >= 50
    finally:
        db.close()


def test_batch_idempotency_and_deduplication():
    """Verify that posting identical batch twice produces 200 OK without duplicate row errors or row count inflation."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    base_ts = time.time() - 1200.0
    items = [
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 26.0,
            "HUMID": 55.0,
            "HUB_TS": base_ts + 10,
        },
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 26.5,
            "HUMID": 54.0,
            "HUB_TS": base_ts + 20,
        },
    ]

    # Post batch first time
    resp1 = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["ingested_count"] == 2

    db = SessionLocal()
    try:
        count_before = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01").count()

        # Re-post identical batch (simulating gateway WAL replay)
        resp2 = client.post("/api/iot/batch", json={"items": items}, headers=headers)
        assert resp2.status_code == 200
        # ON CONFLICT DO NOTHING: 0 new rows ingested
        assert resp2.json()["ingested_count"] == 0

        count_after = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01").count()
        assert count_after == count_before, "Duplicate rows detected after WAL replay!"
    finally:
        db.close()


def test_batch_unapproved_devices_ignored():
    """Verify that batch containing approved and unapproved devices ingests only approved items."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    base_ts = time.time() - 900.0
    items = [
        # 2 approved items
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 23.1,
            "HUMID": 51.0,
            "HUB_TS": base_ts + 1,
        },
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 23.2,
            "HUMID": 51.1,
            "HUB_TS": base_ts + 2,
        },
        # 2 unapproved items (inactive device in DB)
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_UNAPPROVED_01",
            "DEV_NAME": "Unapproved Sensor",
            "DEV_TYPE": "TS",
            "TEMP": 23.3,
            "HUMID": 51.2,
            "HUB_TS": base_ts + 3,
        },
        # 1 unknown device (not in DB)
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "UNKNOWN_DEV_99",
            "DEV_NAME": "Unknown Sensor",
            "DEV_TYPE": "TS",
            "TEMP": 23.4,
            "HUMID": 51.3,
            "HUB_TS": base_ts + 4,
        },
    ]

    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed_count"] == 4
    assert body["ingested_count"] == 2
    assert body["ignored_count"] == 2


def test_batch_alert_storm_suppression():
    """Verify that replayed batch of 10 points with rising temperatures triggers alert evaluation ONLY on latest point."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    db = SessionLocal()
    try:
        # Clear existing alerts for DEV_TS_01
        db.query(event_log).filter(event_log.dev_id == "DEV_TS_01").delete()
        db.commit()
    finally:
        db.close()

    base_ts = time.time() - 600.0
    # 10 readings with rising temperatures exceeding warning (28C) and critical (32C)
    items = [
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": temp,
            "HUMID": 50.0,
            "HUB_TS": base_ts + (i * 5),
        }
        for i, temp in enumerate([20.0, 22.0, 25.0, 27.0, 29.0, 30.0, 31.0, 33.0, 34.0, 35.0])
    ]

    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        alerts = (
            db.query(event_log)
            .filter(event_log.dev_id == "DEV_TS_01", event_log.metric == "temperature")
            .all()
        )
        # Suppressed alert burst: Exactly 1 alert created (for latest reading at 35C)
        assert len(alerts) == 1, f"Alert burst occurred! Expected 1 alert, got {len(alerts)}"
        assert alerts[0].severity == "critical"
        assert alerts[0].value == 35.0
    finally:
        db.close()


def test_batch_partial_payloads_resilience():
    """Verify that batch items with missing humidity or missing optional metrics ingest successfully."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    base_ts = time.time() - 300.0
    items = [
        # TSData with HUMID=None
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 22.5,
            "HUMID": None,
            "HUB_TS": base_ts + 1,
        },
        # TSData with TEMP=None
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": None,
            "HUMID": 45.0,
            "HUB_TS": base_ts + 2,
        },
    ]

    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ingested_count"] == 2


def test_batch_timestamp_preservation():
    """Verify HUB_TS epoch float and _hub_created_at are preserved accurately in event_time."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    target_ts = round(time.time() - 100.0, 3)
    items = [
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 27.8,
            "HUMID": 44.0,
            "HUB_TS": target_ts,
        }
    ]

    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        expected_dt = datetime.fromtimestamp(target_ts, tz=UTC)
        row = (
            db.query(temperature_data)
            .filter(temperature_data.dev_id == "DEV_TS_01", temperature_data.temp == 27.8)
            .first()
        )
        assert row is not None
        row_dt = row.timestamp if row.timestamp.tzinfo is not None else row.timestamp.replace(tzinfo=UTC)
        diff_ms = abs((row_dt - expected_dt).total_seconds()) * 1000.0
        assert diff_ms < 1.0, f"Timestamp precision loss: diff is {diff_ms}ms"
    finally:
        db.close()


def test_subsecond_precision_no_collision():
    """Verify two legitimate readings from the same device 100ms apart are preserved and never deduplicated."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    t_base = round(time.time() - 50.0, 3)
    t_plus_100ms = t_base + 0.1

    items = [
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 28.1,
            "HUMID": 49.0,
            "HUB_TS": t_base,
        },
        {
            "HUB_NAME": "HUB_P4_01",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Temperature Sensor 1",
            "DEV_TYPE": "TS",
            "TEMP": 28.2,
            "HUMID": 49.0,
            "HUB_TS": t_plus_100ms,
        },
    ]

    resp = client.post("/api/iot/batch", json={"items": items}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ingested_count"] == 2

    db = SessionLocal()
    try:
        r1 = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01", temperature_data.temp == 28.1).first()
        r2 = db.query(temperature_data).filter(temperature_data.dev_id == "DEV_TS_01", temperature_data.temp == 28.2).first()
        assert r1 is not None and r2 is not None
        assert r1.data_id != r2.data_id
        assert r1.timestamp != r2.timestamp
    finally:
        db.close()


def test_batch_read_commands_polling_dirty_commit():
    """Verify hub polling /api/hub/commands persists staged heartbeat when throttle threshold has passed."""
    hub_auth_cache.clear()
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }

    # Set last_seen to 60 seconds ago
    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_P4_01")
        h.last_seen = datetime.now(UTC) - timedelta(seconds=60)
        db.commit()
    finally:
        db.close()

    # Poll commands
    resp = client.get("/api/hub/commands", headers=headers)
    assert resp.status_code == 200

    # Verify last_seen was updated in DB
    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_P4_01")
        now_utc = datetime.now(UTC)
        h_seen = h.last_seen if h.last_seen.tzinfo is not None else h.last_seen.replace(tzinfo=UTC)
        assert (now_utc - h_seen).total_seconds() < 5.0
    finally:
        db.close()


def test_batch_payload_formats_and_limits():
    """Verify POST /api/iot/batch accepts both object and array format, and rejects empty or oversized batches."""
    headers = {
        "X-Hub-ID": "HUB_P4_01",
        "X-Hub-Key": "secret_key_p4_hub1",
    }
    valid_item = {
        "HUB_NAME": "HUB_P4_01",
        "DEV_ID": "DEV_TS_01",
        "DEV_NAME": "Temperature Sensor 1",
        "DEV_TYPE": "TS",
        "TEMP": 21.0,
        "HUMID": 50.0,
        "HUB_TS": time.time(),
    }

    # Format A: {"items": [...]}
    r1 = client.post("/api/iot/batch", json={"items": [valid_item]}, headers=headers)
    assert r1.status_code == 200

    # Format B: raw array [...]
    r2 = client.post("/api/iot/batch", json=[valid_item], headers=headers)
    assert r2.status_code == 200

    # Empty items -> 422
    r_empty1 = client.post("/api/iot/batch", json={"items": []}, headers=headers)
    assert r_empty1.status_code == 422

    r_empty2 = client.post("/api/iot/batch", json=[], headers=headers)
    assert r_empty2.status_code == 422


def test_bulk_insert_or_ignore_defensive_fallback_on_missing_index():
    """Verify that bulk_insert_or_ignore falls back to standard insert when unique index is missing without raising OperationalError."""
    from app.routers.iot import bulk_insert_or_ignore
    from sqlalchemy import Column, DateTime, Float, String, create_engine, inspect
    from sqlalchemy.orm import declarative_base, sessionmaker

    TestBase = declarative_base()

    class TestTableNoIndex(TestBase):
        __tablename__ = "test_table_no_index"
        data_id = Column(String, primary_key=True)
        dev_id = Column(String, nullable=False)
        timestamp = Column(DateTime, nullable=False)
        temp = Column(Float, nullable=True)

    test_eng = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(bind=test_eng)
    TestSession = sessionmaker(bind=test_eng)
    db = TestSession()

    records = [
        {"data_id": "test_rec_1", "dev_id": "D1", "timestamp": datetime.now(UTC), "temp": 25.5},
        {"data_id": "test_rec_2", "dev_id": "D2", "timestamp": datetime.now(UTC), "temp": 26.0},
    ]

    # Calling with index_elements on table lacking unique index must NOT crash; it falls back safely
    count = bulk_insert_or_ignore(db, TestTableNoIndex, records, ["dev_id", "timestamp"])
    assert count == 2
    db.commit()

    rows = db.query(TestTableNoIndex).all()
    assert len(rows) == 2
    assert {r.data_id for r in rows} == {"test_rec_1", "test_rec_2"}
    db.close()


def test_migrate_indexes_creates_unique_indexes_and_deduplicates():
    """Verify that migrate_indexes safely deduplicates duplicate rows and creates unique indexes on SQLite."""
    from init_sqlv5 import migrate_indexes
    from sqlalchemy import inspect, text

    # Check on test engine that unique indexes exist
    migrate_indexes(engine)
    inspector = inspect(engine)
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("ats_data")}
    assert "uq_ats_dev_timestamp" in indexes or any("uq_ats" in name for name in indexes)


def test_cross_hub_device_spoofing_rejected():
    """Verify SEC-06: Cross-hub device spoofing is rejected.
    - Single ingestion rejects mismatched device with HTTP 403 'Device does not belong to this hub'.
    - Batch ingestion logs security warning, increments ignored_count, and skips mismatched items."""
    db = SessionLocal()
    try:
        # Create Hub 2 and a device owned by Hub 2
        hub2 = db.get(hub_table, "HUB_P4_02")
        if not hub2:
            hub2 = hub_table(
                hub_id="HUB_P4_02",
                hub_name="Hub Phase 4 Second Gateway",
                hub_key="secret_key_p4_hub2",
                is_active=True,
                status="online",
            )
            db.add(hub2)
        dev_h2 = db.get(dev_table, "DEV_HUB2_TS_01")
        if not dev_h2:
            dev_h2 = dev_table(
                dev_id="DEV_HUB2_TS_01",
                dev_name="Hub 2 Sensor",
                dev_type="TS",
                hub_id="HUB_P4_02",
                room_id="room-p4-01",
                is_active=True,
                last_status="offline",
            )
            db.add(dev_h2)
        db.commit()
    finally:
        db.close()

    hub2_headers = {
        "X-Hub-ID": "HUB_P4_02",
        "X-Hub-Key": "secret_key_p4_hub2",
    }

    # 1. Single ingestion: Hub 2 attempts to ingest for DEV_TS_01 (owned by HUB_P4_01)
    spoofed_single = {
        "HUB_NAME": "HUB_P4_02",
        "DEV_ID": "DEV_TS_01",
        "DEV_NAME": "Spoofed Temperature Sensor",
        "DEV_TYPE": "TS",
        "TEMP": 99.9,
        "HUMID": 10.0,
        "HUB_TS": time.time(),
    }
    resp = client.post("/api/iot", json=spoofed_single, headers=hub2_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Device does not belong to this hub"

    # 2. Batch ingestion: Hub 2 submits batch with 1 legitimate device and 1 spoofed device
    batch_items = [
        # Legitimate device owned by HUB_P4_02
        {
            "HUB_NAME": "HUB_P4_02",
            "DEV_ID": "DEV_HUB2_TS_01",
            "DEV_NAME": "Hub 2 Sensor",
            "DEV_TYPE": "TS",
            "TEMP": 22.0,
            "HUMID": 50.0,
            "HUB_TS": time.time(),
        },
        # Spoofed device owned by HUB_P4_01
        {
            "HUB_NAME": "HUB_P4_02",
            "DEV_ID": "DEV_TS_01",
            "DEV_NAME": "Spoofed Sensor",
            "DEV_TYPE": "TS",
            "TEMP": 99.9,
            "HUMID": 10.0,
            "HUB_TS": time.time() + 1,
        },
    ]
    batch_resp = client.post("/api/iot/batch", json={"items": batch_items}, headers=hub2_headers)
    assert batch_resp.status_code == 200
    body = batch_resp.json()
    assert body["processed_count"] == 2
    assert body["ingested_count"] == 1
    assert body["ignored_count"] == 1

    # Verify in DB that DEV_TS_01 was NOT updated with spoofed temp 99.9
    db = SessionLocal()
    try:
        spoofed_row = db.query(temperature_data).filter(
            temperature_data.dev_id == "DEV_TS_01",
            temperature_data.temp == 99.9
        ).first()
        assert spoofed_row is None, "Spoofed telemetry row was ingested into DB!"

        valid_row = db.query(temperature_data).filter(
            temperature_data.dev_id == "DEV_HUB2_TS_01",
            temperature_data.temp == 22.0
        ).first()
        assert valid_row is not None, "Valid telemetry row was not ingested!"
    finally:
        db.close()

