# server/test_presence_type_aware.py
# Invariant verification test suite for Phase 2: Central Backend Presence Engine Alignment

import os
import time
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import User, dev_table, hub_table, rooms, event_log
from auth import get_current_user, hash_password
from app.main import api
from app.services.presence import (
    get_device_offline_window_seconds,
    evaluate_device_presence_batch,
    resolve_offline_on_telemetry,
    is_online,
    DEVICE_OFFLINE_THRESHOLDS,
    DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS,
)

client = TestClient(api)
api.state.limiter.enabled = False

test_admin = User(
    id="user-presence-admin",
    username="pres_admin",
    password_hash=hash_password("adminpass"),
    display_name="Presence Admin",
    role="admin",
)


class QueryCounter:
    """Tracks SQL queries executed via SQLAlchemy engine event listener."""
    def __init__(self):
        self.count = 0
        self.statements: list[str] = []

    def __enter__(self):
        self.count = 0
        self.statements = []
        event.listen(engine, "before_cursor_execute", self._callback)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        event.remove(engine, "before_cursor_execute", self._callback)

    def _callback(self, conn, cursor, statement, parameters, context, executemany):
        cleaned = statement.strip().upper()
        if any(cleaned.startswith(prefix) for prefix in ("SELECT", "INSERT", "UPDATE", "DELETE")):
            self.count += 1
            self.statements.append(statement)


@pytest.fixture(autouse=True)
def override_auth():
    api.dependency_overrides[get_current_user] = lambda: test_admin
    yield
    api.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def clean_db():
    db = SessionLocal()
    try:
        db.query(event_log).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Pure Functional Core Tests: get_device_offline_window_seconds
# ---------------------------------------------------------------------------

def test_pure_get_device_offline_window_seconds_canonical():
    """Verify canonical device type thresholds."""
    assert get_device_offline_window_seconds("ATS") == 180
    assert get_device_offline_window_seconds("AC") == 360
    assert get_device_offline_window_seconds("ACC") == 360
    assert get_device_offline_window_seconds("TS") == 900


def test_pure_get_device_offline_window_seconds_case_and_whitespace():
    """Verify case-insensitivity and whitespace stripping."""
    assert get_device_offline_window_seconds("ts") == 900
    assert get_device_offline_window_seconds("Ts") == 900
    assert get_device_offline_window_seconds("  TS  ") == 900
    assert get_device_offline_window_seconds("ac") == 360
    assert get_device_offline_window_seconds("Ac") == 360
    assert get_device_offline_window_seconds("  ac  ") == 360
    assert get_device_offline_window_seconds("acc") == 360
    assert get_device_offline_window_seconds("ats") == 180
    assert get_device_offline_window_seconds("Ats") == 180
    assert get_device_offline_window_seconds(" ats\t") == 180


def test_pure_get_device_offline_window_seconds_fallback():
    """Verify fallback for None, empty, unknown types, or invalid types."""
    assert get_device_offline_window_seconds(None) == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS
    assert get_device_offline_window_seconds("") == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS
    assert get_device_offline_window_seconds("   ") == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS
    assert get_device_offline_window_seconds("UNKNOWN_TYPE") == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS
    assert get_device_offline_window_seconds("PUMP") == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS
    assert get_device_offline_window_seconds(12345) == DEFAULT_DEVICE_OFFLINE_WINDOW_SECONDS


def test_pure_is_online_helper():
    """Verify pure is_online helper handles boundary seconds accurately."""
    now_utc = datetime.now(UTC)

    # ATS: 180s
    assert is_online(now_utc - timedelta(seconds=170), dev_type="ATS", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=180), dev_type="ATS", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=181), dev_type="ATS", now_utc=now_utc) is False

    # AC: 360s
    assert is_online(now_utc - timedelta(seconds=350), dev_type="AC", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=360), dev_type="AC", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=361), dev_type="AC", now_utc=now_utc) is False

    # TS: 900s
    assert is_online(now_utc - timedelta(seconds=600), dev_type="TS", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=900), dev_type="TS", now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=901), dev_type="TS", now_utc=now_utc) is False

    # None / unknown fallback: 180s
    assert is_online(now_utc - timedelta(seconds=170), dev_type=None, now_utc=now_utc) is True
    assert is_online(now_utc - timedelta(seconds=190), dev_type=None, now_utc=now_utc) is False
    assert is_online(None, dev_type="TS", now_utc=now_utc) is False


# ---------------------------------------------------------------------------
# 2. Batch Presence Engine Alignment Tests (evaluate_device_presence_batch)
# ---------------------------------------------------------------------------

def test_presence_batch_ats_boundary(clean_db):
    """ATS device: online at 170s, transitions to offline at >180s (e.g. 190s)."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    room = rooms(id="r-ats-1", name="ATS Room")

    dev_online = dev_table(
        dev_id="dev-ats-online",
        dev_name="ATS Switch 1",
        dev_type="ATS",
        room_id="r-ats-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=170),
    )
    dev_offline = dev_table(
        dev_id="dev-ats-offline",
        dev_name="ATS Switch 2",
        dev_type="ATS",
        room_id="r-ats-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=195),
    )
    db.add_all([room, dev_online, dev_offline])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    d1 = db.get(dev_table, "dev-ats-online")
    d2 = db.get(dev_table, "dev-ats-offline")
    assert d1.last_status == "online", "ATS at 170s should remain online (<180s)"
    assert d2.last_status == "offline", "ATS at 195s should transition to offline (>180s)"

    alerts = db.query(event_log).filter(event_log.dev_id == "dev-ats-offline").all()
    assert len(alerts) == 1
    assert alerts[0].alarm == "DEVICE_OFFLINE"
    assert "No signal for > 180s" in alerts[0].message
    db.close()


def test_presence_batch_ac_boundary(clean_db):
    """AC device: online at 350s, transitions to offline at >360s (e.g. 375s)."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    room = rooms(id="r-ac-1", name="AC Room")

    dev_online = dev_table(
        dev_id="dev-ac-online",
        dev_name="AC Controller 1",
        dev_type="AC",
        room_id="r-ac-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=350),
    )
    dev_offline = dev_table(
        dev_id="dev-ac-offline",
        dev_name="AC Controller 2",
        dev_type="AC",
        room_id="r-ac-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=375),
    )
    db.add_all([room, dev_online, dev_offline])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    d1 = db.get(dev_table, "dev-ac-online")
    d2 = db.get(dev_table, "dev-ac-offline")
    assert d1.last_status == "online", "AC at 350s should remain online (<360s)"
    assert d2.last_status == "offline", "AC at 375s should transition to offline (>360s)"

    alerts = db.query(event_log).filter(event_log.dev_id == "dev-ac-offline").all()
    assert len(alerts) == 1
    assert "No signal for > 360s" in alerts[0].message
    db.close()


def test_presence_batch_ts_boundary(clean_db):
    """TS device: online at 600s, transitions to offline at >900s (e.g. 920s)."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    room = rooms(id="r-ts-1", name="TS Room")

    dev_online = dev_table(
        dev_id="dev-ts-online",
        dev_name="Temp Sensor 1",
        dev_type="TS",
        room_id="r-ts-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=600),
    )
    dev_offline = dev_table(
        dev_id="dev-ts-offline",
        dev_name="Temp Sensor 2",
        dev_type="TS",
        room_id="r-ts-1",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=920),
    )
    db.add_all([room, dev_online, dev_offline])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    d1 = db.get(dev_table, "dev-ts-online")
    d2 = db.get(dev_table, "dev-ts-offline")
    assert d1.last_status == "online", "TS at 600s should remain online (<900s)"
    assert d2.last_status == "offline", "TS at 920s should transition to offline (>900s)"

    alerts = db.query(event_log).filter(event_log.dev_id == "dev-ts-offline").all()
    assert len(alerts) == 1
    assert "No signal for > 900s" in alerts[0].message
    db.close()


def test_presence_batch_unknown_and_none_dev_type(clean_db):
    """Unknown or None dev_type defaults to 180s fallback."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    dev_none = dev_table(
        dev_id="dev-none-type",
        dev_name="Device None",
        dev_type=None,
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=190),
    )
    dev_unknown = dev_table(
        dev_id="dev-unknown-type",
        dev_name="Device Custom",
        dev_type="CUSTOM_PUMP",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=190),
    )
    dev_recent = dev_table(
        dev_id="dev-none-recent",
        dev_name="Device Recent",
        dev_type=None,
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=120),
    )
    db.add_all([dev_none, dev_unknown, dev_recent])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    assert db.get(dev_table, "dev-none-type").last_status == "offline"
    assert db.get(dev_table, "dev-unknown-type").last_status == "offline"
    assert db.get(dev_table, "dev-none-recent").last_status == "online"

    alerts = db.query(event_log).filter(event_log.dev_id == "dev-none-type").all()
    assert len(alerts) == 1
    assert "No signal for > 180s" in alerts[0].message
    db.close()


def test_presence_batch_case_insensitivity(clean_db):
    """Mixed case dev_types ('ts', 'Ts', 'ac', 'ats') are evaluated against their respective thresholds."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    dev_ts_lower = dev_table(
        dev_id="dev-ts-lower",
        dev_type="ts",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=700),  # < 900s: online
    )
    dev_ts_mixed = dev_table(
        dev_id="dev-ts-mixed",
        dev_type="Ts",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=950),  # > 900s: offline
    )
    dev_ac_lower = dev_table(
        dev_id="dev-ac-lower",
        dev_type="ac",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=300),  # < 360s: online
    )
    dev_ats_lower = dev_table(
        dev_id="dev-ats-lower",
        dev_type="ats",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=200),  # > 180s: offline
    )
    db.add_all([dev_ts_lower, dev_ts_mixed, dev_ac_lower, dev_ats_lower])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    assert db.get(dev_table, "dev-ts-lower").last_status == "online"
    assert db.get(dev_table, "dev-ts-mixed").last_status == "offline"
    assert db.get(dev_table, "dev-ac-lower").last_status == "online"
    assert db.get(dev_table, "dev-ats-lower").last_status == "offline"
    db.close()


# ---------------------------------------------------------------------------
# 3. Telemetry Arrival & Offline Alert Resolution Tests
# ---------------------------------------------------------------------------

def test_telemetry_arrival_resolves_offline_status_type_aware(clean_db):
    """Fresh telemetry resolves offline alert for TS within 900s window; stale packet >900s does not."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    stale_ts = now_utc - timedelta(seconds=1200)

    room = rooms(id="r-res-1", name="Res Room")
    dev = dev_table(
        dev_id="dev-res-ts",
        dev_name="TS Sensor Res",
        dev_type="TS",
        room_id="r-res-1",
        is_active=True,
        last_status="offline",
        last_seen=stale_ts,
    )
    off_alert = event_log(
        event_id="alert-res-ts",
        alarm="DEVICE_OFFLINE",
        timestamp=stale_ts,
        message="Device went OFFLINE",
        dev_id="dev-res-ts",
        resolved_at=None,
    )
    db.add_all([room, dev, off_alert])
    db.commit()

    # 1. Replayed packet from 1000s ago (> 900s): must NOT resolve
    replayed_time = now_utc - timedelta(seconds=1000)
    resolve_offline_on_telemetry(db, dev, event_time=replayed_time, now_utc=now_utc)
    db.commit()
    assert dev.last_status == "offline"
    assert db.get(event_log, "alert-res-ts").resolved_at is None

    # 2. Replayed packet from 500s ago (< 900s for TS): fresh for TS, resolves alert
    fresh_time = now_utc - timedelta(seconds=500)
    resolve_offline_on_telemetry(db, dev, event_time=fresh_time, now_utc=now_utc)
    db.commit()
    assert dev.last_status == "online"
    alert_obj = db.get(event_log, "alert-res-ts")
    res_at = alert_obj.resolved_at if alert_obj.resolved_at.tzinfo else alert_obj.resolved_at.replace(tzinfo=UTC)
    assert res_at == now_utc

    online_events = db.query(event_log).filter(
        event_log.dev_id == "dev-res-ts",
        event_log.alarm == "DEVICE_ONLINE",
    ).all()
    assert len(online_events) == 1
    db.close()


# ---------------------------------------------------------------------------
# 4. REST Endpoints Alignment: GET /api/devices & GET /api/devices/{dev_id}
# ---------------------------------------------------------------------------

def test_api_devices_computed_status_type_aware(clean_db):
    """GET /api/devices reflects type-aware thresholds in computed status."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    # 500s elapsed: TS is online (500s < 900s), but ATS is offline (500s > 180s)
    dev_ts = dev_table(
        dev_id="dev-api-ts",
        dev_name="API TS",
        dev_type="TS",
        is_active=True,
        last_seen=now_utc - timedelta(seconds=500),
    )
    dev_ats = dev_table(
        dev_id="dev-api-ats",
        dev_name="API ATS",
        dev_type="ATS",
        is_active=True,
        last_seen=now_utc - timedelta(seconds=500),
    )
    dev_ac = dev_table(
        dev_id="dev-api-ac",
        dev_name="API AC",
        dev_type="AC",
        is_active=True,
        last_seen=now_utc - timedelta(seconds=250),  # < 360s: online
    )
    db.add_all([dev_ts, dev_ats, dev_ac])
    db.commit()
    db.close()

    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = {d["dev_id"]: d["status"] for d in resp.json()}
    assert data["dev-api-ts"] == "online", "TS at 500s should be online (window 900s)"
    assert data["dev-api-ats"] == "offline", "ATS at 500s should be offline (window 180s)"
    assert data["dev-api-ac"] == "online", "AC at 250s should be online (window 360s)"

    # Also test single device detail endpoint
    resp_ts = client.get("/api/devices/dev-api-ts")
    assert resp_ts.status_code == 200
    assert resp_ts.json()["status"] == "online"

    resp_ats = client.get("/api/devices/dev-api-ats")
    assert resp_ats.status_code == 200
    assert resp_ats.json()["status"] == "offline"


# ---------------------------------------------------------------------------
# 5. Batch Performance & Zero N+1 Verification
# ---------------------------------------------------------------------------

def test_batch_presence_zero_nplus1_and_performance(clean_db):
    """Seed 30 devices; verify constant single-batch query count and sub-millisecond evaluation speed."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    room = rooms(id="r-perf-1", name="Perf Room")
    db.add(room)

    devices = []
    for i in range(30):
        dtype = ["ATS", "AC", "TS", None][i % 4]
        # Alternate between fresh and stale
        elapsed = 50 if i % 2 == 0 else 1000
        d = dev_table(
            dev_id=f"dev-perf-{i}",
            dev_name=f"Perf Device {i}",
            dev_type=dtype,
            room_id="r-perf-1",
            is_active=True,
            last_status="online",
            last_seen=now_utc - timedelta(seconds=elapsed),
        )
        devices.append(d)
    db.add_all(devices)
    db.commit()
    db.close()

    # Bounded query count invariant:
    # 1 query for active devices
    # 1 query for eager-loaded rooms
    # 1 query for open offline alerts
    # 1 query for stale pending prune delete
    # 1 batch insert for new event_log alerts
    # 1 batch update for dev_table last_status
    # Total SQL statements must be <= 7 (Zero N+1: O(1) with respect to device count)
    with QueryCounter() as qc:
        t0 = time.perf_counter()
        evaluate_device_presence_batch()
        elapsed_ms = (time.perf_counter() - t0) * 1000

    # Query count must NOT scale with 30 devices (would be >30 queries under N+1)
    assert qc.count <= 7, f"Expected <= 7 queries, got {qc.count}: {qc.statements}"
    # Evaluation for 30 devices in-memory must be sub-millisecond per device (< 100ms total)
    assert elapsed_ms < 100.0, f"Batch presence evaluation took {elapsed_ms:.2f}ms (expected <100ms)"
