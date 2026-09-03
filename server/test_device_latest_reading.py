# test_device_latest_reading.py
import os
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    rooms, device_threshold_config, temperature_data, ats_data, data_table
)
from auth import hash_password
from hubgatev5 import api
from test_phase5_presence_nplus1 import QueryCounter

client = TestClient(api)
api.state.limiter.enabled = False


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        admin = User(
            id="user-admin-lr",
            username="admin_lr",
            password_hash=hash_password("adminpass"),
            display_name="Admin LR",
            role="admin"
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()


def get_auth_cookies():
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin_lr", "password": "adminpass"}
    )
    assert resp.status_code == 200
    return resp.cookies


def test_get_devices_populates_latest_reading_and_no_nplus1():
    db = SessionLocal()
    now_utc = datetime.now(UTC)

    # 1. Setup room
    r = rooms(id="r-lr-1", name="Server Room", created_at=now_utc)
    db.add(r)

    # 2. Setup devices
    d_ts = dev_table(dev_id="dev-ts-lr", dev_name="TS Sensor", dev_type="TS", room_id="r-lr-1", is_active=True, last_seen=now_utc)
    d_ats = dev_table(dev_id="dev-ats-lr", dev_name="ATS Unit", dev_type="ATS", room_id="r-lr-1", is_active=True, last_seen=now_utc)
    d_ac = dev_table(dev_id="dev-ac-lr", dev_name="AC Controller", dev_type="AC", room_id="r-lr-1", is_active=True, last_seen=now_utc)
    d_leg = dev_table(dev_id="dev-leg-lr", dev_name="Legacy Device", dev_type="GENERIC", room_id="r-lr-1", is_active=True, last_seen=now_utc)
    d_nodata = dev_table(dev_id="dev-nodata-lr", dev_name="Empty Device", dev_type="TS", room_id="r-lr-1", is_active=True, last_seen=now_utc)

    db.add_all([d_ts, d_ats, d_ac, d_leg, d_nodata])
    db.commit()

    # 3. Add telemetry
    # TS
    ts1 = temperature_data(data_id="ts-lr-1", dev_id="dev-ts-lr", timestamp=now_utc - timedelta(minutes=5), temp=20.0, humid=50.0)
    ts2 = temperature_data(data_id="ts-lr-2", dev_id="dev-ts-lr", timestamp=now_utc - timedelta(minutes=1), temp=28.5, humid=65.2)  # latest
    # ATS
    ats1 = ats_data(
        data_id="ats-lr-1", dev_id="dev-ats-lr", timestamp=now_utc - timedelta(minutes=5),
        state="GENSET", pln=0.0, genset=220.0, aki=11.5, rem_hour=0.0, rem_min=0.0, rem_sec=0.0, auto_mode=True, emergency=True
    )
    ats2 = ats_data(
        data_id="ats-lr-2", dev_id="dev-ats-lr", timestamp=now_utc - timedelta(minutes=1),
        state="PLN", pln=220.5, genset=0.0, aki=12.6, rem_hour=1.0, rem_min=0.0, rem_sec=0.0, auto_mode=True, emergency=False
    )  # latest
    # AC
    ac_ts = temperature_data(data_id="ac-lr-1", dev_id="dev-ac-lr", timestamp=now_utc - timedelta(minutes=1), temp=24.0, humid=55.0)
    ac_dt = data_table(
        data_id="ac-dt-lr", dev_id="dev-ac-lr", timestamp=now_utc - timedelta(minutes=1),
        payload={"AC1_POWER": "ON", "AC1_TEMP": 22.0, "AC2_POWER": "OFF", "AC2_TEMP": 25.0}
    )
    # Legacy
    leg_dt = data_table(
        data_id="leg-dt-lr", dev_id="dev-leg-lr", timestamp=now_utc - timedelta(minutes=1),
        payload={"power_kw": 12.4, "status": "running"}
    )

    db.add_all([ts1, ts2, ats1, ats2, ac_ts, ac_dt, leg_dt])
    db.commit()
    db.close()

    cookies = get_auth_cookies()

    # Query with bounded query counter
    with QueryCounter() as qc:
        resp = client.get("/api/devices?status=all", cookies=cookies)

    assert resp.status_code == 200
    devices_data = resp.json()
    assert len(devices_data) >= 5

    by_id = {d["dev_id"]: d for d in devices_data}

    # 1. TS sensor check
    ts_dev = by_id["dev-ts-lr"]
    assert "latest_reading" in ts_dev
    assert ts_dev["latest_reading"] is not None
    assert ts_dev["latest_reading"]["temp"] == 28.5
    assert ts_dev["latest_reading"]["humid"] == 65.2
    assert ts_dev["latest_reading"]["timestamp"].endswith("+00:00") or ts_dev["latest_reading"]["timestamp"].endswith("Z")

    # 2. ATS unit check
    ats_dev = by_id["dev-ats-lr"]
    assert "latest_reading" in ats_dev
    assert ats_dev["latest_reading"] is not None
    assert ats_dev["latest_reading"]["state"] == "PLN"
    assert ats_dev["latest_reading"]["pln"] == 220.5
    assert ats_dev["latest_reading"]["aki"] == 12.6
    assert ats_dev["latest_reading"]["timestamp"].endswith("+00:00") or ats_dev["latest_reading"]["timestamp"].endswith("Z")

    # 3. AC controller check
    ac_dev = by_id["dev-ac-lr"]
    assert "latest_reading" in ac_dev
    assert ac_dev["latest_reading"] is not None
    assert ac_dev["latest_reading"]["temp"] == 24.0
    assert ac_dev["latest_reading"]["ac1_power"] == "ON"
    assert ac_dev["latest_reading"]["ac2_power"] == "OFF"
    assert ac_dev["latest_reading"]["timestamp"].endswith("+00:00") or ac_dev["latest_reading"]["timestamp"].endswith("Z")

    # 4. Legacy device check
    leg_dev = by_id["dev-leg-lr"]
    assert "latest_reading" in leg_dev
    assert leg_dev["latest_reading"] is not None
    assert leg_dev["latest_reading"]["power_kw"] == 12.4
    assert leg_dev["latest_reading"]["timestamp"].endswith("+00:00") or leg_dev["latest_reading"]["timestamp"].endswith("Z")

    # 5. Empty device check
    empty_dev = by_id["dev-nodata-lr"]
    assert "latest_reading" in empty_dev
    assert empty_dev["latest_reading"] is None

    # Query count must be O(1) bounded - strictly <= 11 queries regardless of device count
    # (4 for auth session/user, 3 for devices + selectinloads, 3 for batched telemetry)
    assert qc.count <= 11, f"Expected <= 11 queries, got {qc.count}: {qc.statements}"

    # Single device GET endpoint check
    resp_single_ts = client.get("/api/devices/dev-ts-lr", cookies=cookies)
    assert resp_single_ts.status_code == 200
    assert resp_single_ts.json()["latest_reading"]["temp"] == 28.5
    assert resp_single_ts.json()["latest_reading"]["timestamp"].endswith("+00:00") or resp_single_ts.json()["latest_reading"]["timestamp"].endswith("Z")

    resp_single_ats = client.get("/api/devices/dev-ats-lr", cookies=cookies)
    assert resp_single_ats.status_code == 200
    assert resp_single_ats.json()["latest_reading"]["state"] == "PLN"
    assert resp_single_ats.json()["latest_reading"]["timestamp"].endswith("+00:00") or resp_single_ats.json()["latest_reading"]["timestamp"].endswith("Z")


def test_format_ts_helper_enforces_utc():
    from app.services.telemetry import _format_ts

    assert _format_ts(None) is None
    assert _format_ts("") is None

    # Naive datetime gets converted to UTC ISO format with +00:00
    naive_dt = datetime(2026, 9, 3, 12, 0, 0)
    formatted = _format_ts(naive_dt)
    assert formatted == "2026-09-03T12:00:00+00:00"

    # Aware datetime preserves timezone
    aware_dt = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    assert _format_ts(aware_dt) == "2026-09-03T12:00:00+00:00"
