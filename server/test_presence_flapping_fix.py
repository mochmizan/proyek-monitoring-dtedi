# server/test_presence_flapping_fix.py
# Reproduction and verification tests for presence flapping and replay timestamp handling.

import os
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import User, dev_table, hub_table, rooms, event_log
from auth import get_current_user, hash_password
from app.main import api
from app.services.presence import (
    evaluate_device_presence_batch,
    resolve_offline_on_telemetry,
    DEVICE_OFFLINE_WINDOW_SECONDS,
    PRESENCE_INTERVAL_SECONDS,
)

client = TestClient(api)

test_admin = User(
    id="user-flap-admin",
    username="flap_admin",
    password_hash=hash_password("adminpass"),
    display_name="Flap Admin",
    role="admin",
)

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


def test_presence_tolerance_margin_keeps_device_online_at_40s(clean_db):
    """A device last seen 40s ago must NOT be declared OFFLINE when tolerance is 60s.
    Under the legacy 25s window, a 40s packet gap caused false OFFLINE flapping.
    """
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    seen_40s_ago = now_utc - timedelta(seconds=40)

    room = rooms(id="r-tol-1", name="Server Room")
    dev = dev_table(
        dev_id="dev-tol-1",
        dev_name="TS Sensor",
        dev_type="TS",
        room_id="r-tol-1",
        is_active=True,
        last_status="online",
        last_seen=seen_40s_ago,
    )
    db.add_all([room, dev])
    db.commit()
    db.close()

    evaluate_device_presence_batch()

    db = SessionLocal()
    dev_after = db.get(dev_table, "dev-tol-1")
    assert dev_after.last_status == "online", "Device should remain ONLINE at 40s under 60s tolerance window"
    open_alerts = db.query(event_log).filter(
        event_log.dev_id == "dev-tol-1",
        event_log.alarm == "DEVICE_OFFLINE",
        event_log.resolved_at.is_(None),
    ).all()
    assert len(open_alerts) == 0, "No false DEVICE_OFFLINE alert should be generated"
    db.close()


def test_stale_wal_replay_does_not_falsely_mark_device_online(clean_db):
    """When a device is OFFLINE and an old replayed packet arrives (e.g. from 2 hours ago),
    resolve_offline_on_telemetry must NOT mark the device online or resolve its offline alerts.
    """
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    two_hours_ago = now_utc - timedelta(hours=2)

    room = rooms(id="r-wal-1", name="Server Room")
    dev = dev_table(
        dev_id="dev-wal-1",
        dev_name="ATS Unit",
        dev_type="ATS",
        room_id="r-wal-1",
        is_active=True,
        last_status="offline",
        last_seen=two_hours_ago,
    )
    db.add_all([room, dev])

    off_alert = event_log(
        event_id="alert-wal-1",
        alarm="DEVICE_OFFLINE",
        timestamp=two_hours_ago,
        message="Device went OFFLINE",
        dev_id="dev-wal-1",
        resolved_at=None,
    )
    db.add(off_alert)
    db.commit()

    # Simulate replaying a packet that occurred 1 hour ago (still stale)
    replayed_time = now_utc - timedelta(hours=1)
    resolve_offline_on_telemetry(db, dev, event_time=replayed_time, now_utc=now_utc)
    db.commit()

    dev_seen = dev.last_seen if dev.last_seen.tzinfo else dev.last_seen.replace(tzinfo=UTC)
    assert dev_seen == replayed_time, "last_seen should reflect event_time, not now_utc"

    alert_after = db.get(event_log, "alert-wal-1")
    assert alert_after.resolved_at is None, "Open offline alert must NOT be resolved by stale replayed telemetry"

    online_events = db.query(event_log).filter(
        event_log.dev_id == "dev-wal-1",
        event_log.alarm == "DEVICE_ONLINE",
    ).all()
    assert len(online_events) == 0, "No spurious DEVICE_ONLINE event should be created for stale replay"
    db.close()


def test_monotonic_last_seen_preserves_latest_timestamp(clean_db):
    """If an out-of-order or replayed packet arrives with an older timestamp than current last_seen,
    last_seen must NOT roll backward into the past.
    """
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    t_recent = now_utc - timedelta(seconds=5)
    t_older = now_utc - timedelta(seconds=50)

    dev = dev_table(
        dev_id="dev-mono-1",
        dev_name="AC Unit",
        dev_type="AC",
        is_active=True,
        last_status="online",
        last_seen=t_recent,
    )
    db.add(dev)
    db.commit()

    # Older packet arrives
    resolve_offline_on_telemetry(db, dev, event_time=t_older, now_utc=now_utc)
    db.commit()

    dev_seen = dev.last_seen if dev.last_seen.tzinfo else dev.last_seen.replace(tzinfo=UTC)
    assert dev_seen == t_recent, "last_seen must not roll backward on out-of-order packet"
    assert dev.last_status == "online"
    db.close()


def test_fresh_telemetry_recovers_offline_device(clean_db):
    """Fresh telemetry (within tolerance window) must resolve offline alerts and mark online."""
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    t_stale = now_utc - timedelta(seconds=1000)

    room = rooms(id="r-fresh-1", name="Server Room")
    dev = dev_table(
        dev_id="dev-fresh-1",
        dev_name="TS Sensor",
        dev_type="TS",
        room_id="r-fresh-1",
        is_active=True,
        last_status="offline",
        last_seen=t_stale,
    )
    off_alert = event_log(
        event_id="alert-fresh-1",
        alarm="DEVICE_OFFLINE",
        timestamp=t_stale,
        message="Device went OFFLINE",
        dev_id="dev-fresh-1",
        resolved_at=None,
    )
    db.add_all([room, dev, off_alert])
    db.commit()

    # Fresh telemetry arrives
    t_fresh = now_utc - timedelta(seconds=2)
    resolve_offline_on_telemetry(db, dev, event_time=t_fresh, now_utc=now_utc)
    db.commit()

    assert dev.last_status == "online"
    dev_seen = dev.last_seen if dev.last_seen.tzinfo else dev.last_seen.replace(tzinfo=UTC)
    assert dev_seen == t_fresh

    alert_after = db.get(event_log, "alert-fresh-1")
    res_at = alert_after.resolved_at if alert_after.resolved_at.tzinfo else alert_after.resolved_at.replace(tzinfo=UTC)
    assert res_at == now_utc, "Offline alert should be resolved"

    online_events = db.query(event_log).filter(
        event_log.dev_id == "dev-fresh-1",
        event_log.alarm == "DEVICE_ONLINE",
    ).all()
    assert len(online_events) == 1
    db.close()
