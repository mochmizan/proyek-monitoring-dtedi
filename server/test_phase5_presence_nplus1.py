# test_phase5_presence_nplus1.py
# Verification Test Suite for Phase 5: Decoupled Presence Background Job & N+1 Query Elimination

import asyncio
import os
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import (
    User, UserSession, dev_table, hub_table, rooms,
    device_threshold_config, temperature_data, ats_data, data_table,
    event_log, schedules
)
from auth import get_current_user, hash_password
from app.main import api
from app.services.presence import (
    evaluate_device_presence_batch,
    PRESENCE_INTERVAL_SECONDS,
    DEVICE_OFFLINE_WINDOW_SECONDS
)

client = TestClient(api)
api.state.limiter.enabled = False

test_admin_user = User(
    id="user-phase5-admin",
    username="admin_p5",
    password_hash=hash_password("adminpass"),
    display_name="Admin Phase 5",
    role="admin",
)


class QueryCounter:
    """Tracks SQL queries executed via SQLAlchemy engine event listener."""
    def __init__(self):
        self.count = 0
        self.statements: list[str] = []
        self.writes: list[str] = []

    def __enter__(self):
        self.count = 0
        self.statements = []
        self.writes = []
        event.listen(engine, "before_cursor_execute", self._callback)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        event.remove(engine, "before_cursor_execute", self._callback)

    def _callback(self, conn, cursor, statement, parameters, context, executemany):
        cleaned = statement.strip().upper()
        # Count non-transactional SQL statements
        if any(cleaned.startswith(prefix) for prefix in ("SELECT", "INSERT", "UPDATE", "DELETE")):
            self.count += 1
            self.statements.append(statement)
        if any(cleaned.startswith(prefix) for prefix in ("INSERT", "UPDATE", "DELETE")):
            self.writes.append(statement)


@pytest.fixture(autouse=True)
def override_auth():
    api.dependency_overrides[get_current_user] = lambda: test_admin_user
    yield
    api.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def clean_db():
    db = SessionLocal()
    try:
        db.query(event_log).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(device_threshold_config).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(schedules).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Task 1: Background Presence Engine Tests
# ---------------------------------------------------------------------------

def test_presence_worker_offline_detection(clean_db):
    """Active device with last_seen > 25s ago transitions to offline and creates 1 alert."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    stale_time = now_utc - timedelta(seconds=35)

    room = rooms(id="r-pres-1", name="Presence Room 1")
    dev = dev_table(
        dev_id="dev-pres-1",
        dev_name="Sensor 1",
        dev_type="TS",
        room_id="r-pres-1",
        is_active=True,
        last_status="online",
        last_seen=stale_time,
    )
    db.add_all([room, dev])
    db.commit()
    db.close()

    # First evaluation: triggers offline transition
    evaluate_device_presence_batch()

    db = SessionLocal()
    d_after = db.get(dev_table, "dev-pres-1")
    assert d_after.last_status == "offline"

    alerts = db.query(event_log).filter(
        event_log.dev_id == "dev-pres-1",
        event_log.alarm == "DEVICE_OFFLINE"
    ).all()
    assert len(alerts) == 1
    assert alerts[0].resolved_at is None
    assert "Sensor 1" in alerts[0].message
    db.close()

    # Second evaluation: device already offline; must NOT create duplicate alerts
    evaluate_device_presence_batch()

    db = SessionLocal()
    alerts_after = db.query(event_log).filter(
        event_log.dev_id == "dev-pres-1",
        event_log.alarm == "DEVICE_OFFLINE"
    ).all()
    assert len(alerts_after) == 1
    db.close()


def test_presence_worker_online_recovery(clean_db):
    """When an offline device sends a recent signal, worker resolves the open alert and sets online."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    stale_time = now_utc - timedelta(seconds=40)

    room = rooms(id="r-rec-1", name="Recovery Room")
    dev = dev_table(
        dev_id="dev-rec-1",
        dev_name="Recovering Device",
        dev_type="TS",
        room_id="r-rec-1",
        is_active=True,
        last_status="online",
        last_seen=stale_time,
    )
    db.add_all([room, dev])
    db.commit()
    db.close()

    # Step 1: Device goes offline
    evaluate_device_presence_batch()

    db = SessionLocal()
    alert = db.query(event_log).filter(
        event_log.dev_id == "dev-rec-1",
        event_log.alarm == "DEVICE_OFFLINE",
        event_log.resolved_at.is_(None)
    ).first()
    assert alert is not None

    # Step 2: Device signal recovers
    d = db.get(dev_table, "dev-rec-1")
    d.last_seen = datetime.now(UTC)
    db.commit()
    db.close()

    # Step 3: Run worker to evaluate recovery
    evaluate_device_presence_batch()

    db = SessionLocal()
    d_recovered = db.get(dev_table, "dev-rec-1")
    assert d_recovered.last_status == "online"

    open_alerts = db.query(event_log).filter(
        event_log.dev_id == "dev-rec-1",
        event_log.alarm == "DEVICE_OFFLINE",
        event_log.resolved_at.is_(None)
    ).all()
    assert len(open_alerts) == 0

    resolved_alert = db.query(event_log).filter(
        event_log.dev_id == "dev-rec-1",
        event_log.alarm == "DEVICE_OFFLINE"
    ).first()
    assert resolved_alert is not None
    assert resolved_alert.resolved_at is not None
    db.close()


def test_presence_worker_stale_pending_pruning(clean_db):
    """Stale unapproved devices older than 25s are pruned; recent unapproved devices preserved."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    stale_unapproved = dev_table(
        dev_id="dev-stale-pending",
        dev_name="Stale Pending",
        dev_type="TS",
        is_active=False,
        room_id=None,
        created_at=now_utc - timedelta(seconds=60),
    )
    recent_unapproved = dev_table(
        dev_id="dev-recent-pending",
        dev_name="Recent Pending",
        dev_type="TS",
        is_active=False,
        room_id=None,
        created_at=now_utc - timedelta(seconds=5),
    )
    approved_device = dev_table(
        dev_id="dev-approved-stale",
        dev_name="Approved Active",
        dev_type="TS",
        is_active=True,
        room_id=None,
        created_at=now_utc - timedelta(seconds=60),
    )
    db.add_all([stale_unapproved, recent_unapproved, approved_device])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    assert db.get(dev_table, "dev-stale-pending") is None
    assert db.get(dev_table, "dev-recent-pending") is not None
    assert db.get(dev_table, "dev-approved-stale") is not None
    db.close()


def test_presence_worker_error_recovery():
    """Worker catches DB errors, calls rollback and close, and does not leak exceptions."""
    with patch("app.services.presence.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.side_effect = RuntimeError("Simulated Database Outage")

        # Worker must catch exception and handle gracefully
        evaluate_device_presence_batch()

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Task 2: Strictly Read-Only Idempotent GET /api/devices
# ---------------------------------------------------------------------------

def test_get_devices_read_only_and_idempotent(clean_db):
    """GET /api/devices produces 0 database writes and returns identical results repeatedly."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    room = rooms(id="r-dev-ro", name="Read-Only Room")
    d1 = dev_table(
        dev_id="dev-ro-1",
        dev_name="RO Device 1",
        dev_type="TS",
        room_id="r-dev-ro",
        is_active=True,
        last_status="online",
        last_seen=now_utc - timedelta(seconds=50),  # timed out, but read must NOT mutate DB
    )
    cfg1 = device_threshold_config(
        dev_id="dev-ro-1",
        warning=30.0,
        critical=40.0,
        hysteresis=0.5,
        debounce_seconds=60,
    )
    d2 = dev_table(
        dev_id="dev-ro-2",
        dev_name="RO Device 2",
        dev_type="ATS",
        room_id="r-dev-ro",
        is_active=False,
    )
    db.add_all([room, d1, cfg1, d2])
    db.commit()
    initial_alerts_count = db.query(event_log).count()
    db.close()

    # Call GET /api/devices 3 times
    for _ in range(3):
        with QueryCounter() as qc:
            resp = client.get("/api/devices")
        assert resp.status_code == 200
        # Verify ZERO write operations executed
        assert len(qc.writes) == 0, f"Expected 0 writes, got {qc.writes}"

    # Verify event_log was not touched
    db = SessionLocal()
    assert db.query(event_log).count() == initial_alerts_count
    # Verify device last_status was not mutated in database by GET
    d1_check = db.get(dev_table, "dev-ro-1")
    assert d1_check.last_status == "online"
    db.close()


def test_get_device_detail_eager_loading(clean_db):
    """GET /api/devices/{dev_id} eagerly loads threshold_config and room."""
    db = SessionLocal()
    room = rooms(id="r-single", name="Single Room")
    dev = dev_table(
        dev_id="dev-single-1",
        dev_name="Single Sensor",
        dev_type="TS",
        room_id="r-single",
        is_active=True,
    )
    cfg = device_threshold_config(
        dev_id="dev-single-1",
        warning=25.0,
        critical=35.0,
        hysteresis=0.5,
        debounce_seconds=30,
    )
    db.add_all([room, dev, cfg])
    db.commit()
    db.close()

    resp = client.get("/api/devices/dev-single-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dev_id"] == "dev-single-1"
    assert data["threshold_config"] is not None
    assert data["threshold_config"]["warning"] == 25.0


# ---------------------------------------------------------------------------
# Task 4: N+1 Elimination in rooms.py
# ---------------------------------------------------------------------------

def test_list_rooms_single_query(clean_db):
    """GET /api/rooms executes exactly 1 SQL query with device count aggregation."""
    db = SessionLocal()
    r1 = rooms(id="r-cnt-1", name="Room Alpha")
    r2 = rooms(id="r-cnt-2", name="Room Beta")
    r3 = rooms(id="r-cnt-3", name="Room Gamma")

    # r1 has 3 devices, r2 has 1 device, r3 has 0 devices
    devs = [
        dev_table(dev_id="d-a1", room_id="r-cnt-1", is_active=True),
        dev_table(dev_id="d-a2", room_id="r-cnt-1", is_active=True),
        dev_table(dev_id="d-a3", room_id="r-cnt-1", is_active=False),
        dev_table(dev_id="d-b1", room_id="r-cnt-2", is_active=True),
    ]
    db.add_all([r1, r2, r3] + devs)
    db.commit()
    db.close()

    with QueryCounter() as qc:
        resp = client.get("/api/rooms")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    counts = {r["name"]: r["device_count"] for r in data}
    assert counts["Room Alpha"] == 3
    assert counts["Room Beta"] == 1
    assert counts["Room Gamma"] == 0

    assert qc.count == 1, f"Expected exactly 1 SQL query, got {qc.count}: {qc.statements}"


def test_get_room_map_indexed_queries(clean_db):
    """GET /api/rooms/{id}/map returns latest readings with bounded per-device queries leveraging (dev_id, timestamp DESC) index."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    room_id = "r-map-test"
    room = rooms(id=room_id, name="Floor Map Room")
    d_ts1 = dev_table(dev_id="dev-ts-1", dev_name="TS Sensor 1", dev_type="TS", room_id=room_id, is_active=True)
    d_ts2 = dev_table(dev_id="dev-ts-2", dev_name="TS Sensor 2", dev_type="TS", room_id=room_id, is_active=True)
    d_ats = dev_table(dev_id="dev-ats-1", dev_name="ATS Panel", dev_type="ATS", room_id=room_id, is_active=True)
    d_leg = dev_table(dev_id="dev-leg-1", dev_name="Legacy Dev", dev_type="CUSTOM", room_id=room_id, is_active=True)
    d_ac = dev_table(dev_id="dev-ac-1", dev_name="AC Controller", dev_type="AC", room_id=room_id, is_active=True)

    # Add historical rows (older and newer)
    ts_rows = [
        temperature_data(data_id="td-1", dev_id="dev-ts-1", timestamp=now_utc - timedelta(minutes=10), temp=20.0, humid=50.0),
        temperature_data(data_id="td-2", dev_id="dev-ts-1", timestamp=now_utc - timedelta(minutes=1), temp=28.5, humid=65.0),  # latest
        temperature_data(data_id="td-3", dev_id="dev-ts-2", timestamp=now_utc - timedelta(minutes=5), temp=22.0, humid=52.0),
        temperature_data(data_id="td-4", dev_id="dev-ts-2", timestamp=now_utc - timedelta(minutes=2), temp=24.0, humid=55.0),  # latest
        temperature_data(data_id="td-5", dev_id="dev-ac-1", timestamp=now_utc - timedelta(minutes=1), temp=23.5, humid=58.0),  # latest AC temp
    ]
    ats_rows = [
        ats_data(
            data_id="ad-1",
            dev_id="dev-ats-1",
            timestamp=now_utc - timedelta(minutes=10),
            pln=210.0,
            genset=0.0,
            aki=12.5,
            rem_hour=0.0,
            rem_min=0.0,
            rem_sec=0.0,
            auto_mode=True,
            emergency=False,
            state="1",
        ),
        ats_data(
            data_id="ad-2",
            dev_id="dev-ats-1",
            timestamp=now_utc - timedelta(minutes=1),
            pln=0.0,
            genset=225.0,
            aki=13.0,
            rem_hour=1.0,
            rem_min=30.0,
            rem_sec=0.0,
            auto_mode=False,
            emergency=False,
            state="2",
        ),
    ]
    legacy_rows = [
        data_table(data_id="ld-1", dev_id="dev-leg-1", timestamp=now_utc - timedelta(minutes=10), payload={"val": "old"}),
        data_table(data_id="ld-2", dev_id="dev-leg-1", timestamp=now_utc - timedelta(minutes=3), payload={"val": "newest"}),  # latest
        data_table(data_id="ld-3", dev_id="dev-ac-1", timestamp=now_utc - timedelta(minutes=1), payload={"AC1_POWER": "ON", "AC1_TEMP": 24.0, "AC2_POWER": "OFF", "AC2_TEMP": 26.0}),
    ]

    db.add_all([room, d_ts1, d_ts2, d_ats, d_leg, d_ac] + ts_rows + ats_rows + legacy_rows)
    db.commit()
    db.close()

    with QueryCounter() as qc:
        resp = client.get(f"/api/rooms/{room_id}/map")

    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == "r-map-test"
    assert len(data["devices"]) == 5

    markers = {m["dev_id"]: m for m in data["devices"]}
    assert markers["dev-ts-1"]["latest_reading"]["temp"] == 28.5
    assert markers["dev-ts-2"]["latest_reading"]["temp"] == 24.0
    assert markers["dev-ats-1"]["latest_reading"]["genset"] == 225.0
    assert markers["dev-leg-1"]["latest_reading"]["val"] == "newest"
    assert markers["dev-ac-1"]["latest_reading"]["temp"] == 23.5
    assert markers["dev-ac-1"]["latest_reading"]["humid"] == 58.0
    assert markers["dev-ac-1"]["latest_reading"]["ac1_power"] == "ON"
    assert markers["dev-ac-1"]["latest_reading"]["ac1_temp"] == 24.0
    assert markers["dev-ac-1"]["latest_reading"]["ac2_power"] == "OFF"
    assert markers["dev-ac-1"]["latest_reading"]["ac2_temp"] == 26.0

    # Query count bounded per device leveraging B-tree index (1 for room+devices, 1 per device lookup + 1 for AC payload merge)
    assert qc.count <= len(data["devices"]) + 3, f"Expected <= {len(data['devices']) + 3} queries, got {qc.count}: {qc.statements}"


# ---------------------------------------------------------------------------
# Task 5: Hub Group BY Aggregation
# ---------------------------------------------------------------------------

def test_list_hubs_group_by(clean_db):
    """GET /api/hubs aggregates devices with bounded queries (= 2) and excludes orphans."""
    db = SessionLocal()
    h1 = hub_table(hub_id="hub-alpha", hub_name="Hub Alpha", hub_key="k1", is_active=True)
    h2 = hub_table(hub_id="hub-beta", hub_name="Hub Beta", hub_key="k2", is_active=True)

    d1 = dev_table(dev_id="d-hub-1", dev_name="Hub1 Dev 1", dev_type="TS", hub_id="hub-alpha", is_active=True)
    d2 = dev_table(dev_id="d-hub-2", dev_name="Hub1 Dev 2", dev_type="ATS", hub_id="hub-alpha", is_active=True)
    d_orphan = dev_table(dev_id="d-orphan", dev_name="Orphan", dev_type="TS", hub_id=None, is_active=False)

    db.add_all([h1, h2, d1, d2, d_orphan])
    db.commit()
    db.close()

    with QueryCounter() as qc:
        resp = client.get("/api/hubs")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    hubs = {h["hub_id"]: h for h in data}
    assert hubs["hub-alpha"]["device_count"] == 2
    assert len(hubs["hub-alpha"]["devices"]) == 2
    assert hubs["hub-beta"]["device_count"] == 0
    assert len(hubs["hub-beta"]["devices"]) == 0

    all_dev_ids = [dev["dev_id"] for h in data for dev in h["devices"]]
    assert "d-orphan" not in all_dev_ids

    # Query count must be bounded at exactly 2 queries
    assert qc.count == 2, f"Expected 2 queries, got {qc.count}: {qc.statements}"


# ---------------------------------------------------------------------------
# Task 3: Scheduler Lifespan Batch Startup
# ---------------------------------------------------------------------------

def test_scheduler_startup_single_session(clean_db):
    """Scheduler lifespan registers presence worker and enabled schedules."""
    db = SessionLocal()
    hub = hub_table(hub_id="hub-alpha", hub_name="Hub Alpha", hub_key="k1", is_active=True)
    dev = dev_table(dev_id="dev-ats-1", dev_name="ATS 1", dev_type="ATS", hub_id="hub-alpha", is_active=True)
    db.add_all([hub, dev])
    db.commit()

    s1 = schedules(
        id="sch-test-1",
        cron_expr="0 8 * * *",
        tz="Asia/Jakarta",
        enabled=True,
        created_by="admin",
        dev_id="dev-ats-1",
        hub_id="hub-alpha",
        payload={"mode": "manual", "start_genset": "on"},
    )
    s2 = schedules(
        id="sch-test-2",
        cron_expr="0 18 * * *",
        tz="Asia/Jakarta",
        enabled=True,
        created_by="admin",
        dev_id="dev-ats-1",
        hub_id="hub-alpha",
        payload={"mode": "auto"},
    )
    db.add_all([s1, s2])
    db.commit()
    db.close()

    async def run_lifespan():
        from app.services.scheduler import scheduler_lifespan
        import app.services.scheduler as sched_mod

        async with scheduler_lifespan(api):
            sched = sched_mod.scheduler
            assert sched is not None
            assert sched.running
            assert sched.get_job("engine-device-presence") is not None
            assert sched.get_job("schedule-sch-test-1") is not None
            assert sched.get_job("schedule-sch-test-2") is not None

    asyncio.run(run_lifespan())

    # Verify next_run_at was persisted in DB
    db = SessionLocal()
    s1_check = db.get(schedules, "sch-test-1")
    assert s1_check.next_run_at is not None
    db.close()
