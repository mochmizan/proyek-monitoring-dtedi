# test_alert_evaluation.py
# Test Suite for Milestone 4: Alert Threshold Evaluation Backend in HubGate V5

import os
import sys
import uuid
import datetime
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    rooms, device_threshold_config, temperature_data, ats_data, data_table,
    event_log
)
from auth import hash_password
from hubgatev5 import api

client = TestClient(api)
api.state.limiter.enabled = False

TEST_HUB_ID = "HUB_TEST_M4"
TEST_HUB_KEY = "secret_key_m4"


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        # Clear tables for clean module isolation
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(event_log).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Create test users with argon2id hashed passwords
        admin = User(
            id="user-admin-m4",
            username="admin_m4",
            password_hash=hash_password("adminpass"),
            display_name="Admin M4",
            role="admin"
        )
        operator = User(
            id="user-operator-m4",
            username="operator_m4",
            password_hash=hash_password("operatorpass"),
            display_name="Operator M4",
            role="operator"
        )
        viewer = User(
            id="user-viewer-m4",
            username="viewer_m4",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer M4",
            role="viewer"
        )
        db.add_all([admin, operator, viewer])

        # Create default test hub
        hub = hub_table(
            hub_id=TEST_HUB_ID,
            hub_name="Edge Hub Test M4",
            hub_key=TEST_HUB_KEY,
            is_active=True
        )
        db.add(hub)

        # Create test rooms
        room_server = rooms(
            id="room_server_m4",
            name="Server Room M4",
            hub_id=TEST_HUB_ID,
            created_at=datetime.now(UTC)
        )
        room_generator = rooms(
            id="room_gen_m4",
            name="Generator Room M4",
            hub_id=TEST_HUB_ID,
            created_at=datetime.now(UTC)
        )
        db.add_all([room_server, room_generator])

        # Create test devices
        dev_ts = dev_table(
            dev_id="AA:BB:CC:11:22:33",
            dev_name="Temp Sensor Server",
            dev_type="TS",
            hub_id=TEST_HUB_ID,
            room_id="room_server_m4",
            is_active=True,
            created_at=datetime.now(UTC)
        )
        dev_ats = dev_table(
            dev_id="AA:BB:CC:44:55:66",
            dev_name="ATS Generator Unit",
            dev_type="ATS",
            hub_id=TEST_HUB_ID,
            room_id="room_gen_m4",
            is_active=True,
            created_at=datetime.now(UTC)
        )
        dev_nodefault = dev_table(
            dev_id="AA:BB:CC:77:88:99",
            dev_name="Temp Sensor Default Thresh",
            dev_type="TS",
            hub_id=TEST_HUB_ID,
            room_id="room_server_m4",
            is_active=True,
            created_at=datetime.now(UTC)
        )
        db.add_all([dev_ts, dev_ats, dev_nodefault])

        # Add custom threshold config to dev_ts
        thresh_ts = device_threshold_config(
            dev_id="AA:BB:CC:11:22:33",
            warning=28.0,
            critical=32.0,
            hysteresis=0.5,
            debounce_seconds=60
        )
        db.add(thresh_ts)

        db.commit()
    finally:
        db.close()


def get_auth_cookies(username: str, password: str) -> dict:
    """Helper to log in and retrieve session cookie."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


def get_hub_headers() -> dict:
    """Helper to provide edge hub auth headers."""
    return {
        "X-Hub-ID": TEST_HUB_ID,
        "X-Hub-Key": TEST_HUB_KEY
    }


# ==========================================
# 1. THRESHOLD UPDATE ENDPOINT (Task 4.1)
# ==========================================

def test_threshold_config_admin_success():
    admin_cookies = get_auth_cookies("admin_m4", "adminpass")
    
    # Update thresholds for dev_ts
    payload = {
        "warning": 26.5,
        "critical": 30.5,
        "hysteresis": 0.8,
        "debounce_seconds": 90
    }
    resp = client.put(
        "/api/devices/AA:BB:CC:11:22:33/thresholds",
        json=payload,
        cookies=admin_cookies
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["warning"] == 26.5
    assert data["critical"] == 30.5
    assert data["hysteresis"] == 0.8
    assert data["debounce_seconds"] == 90

    # Verify directly in DB
    db = SessionLocal()
    try:
        cfg = db.get(device_threshold_config, "AA:BB:CC:11:22:33")
        assert cfg is not None
        assert cfg.warning == 26.5
        assert cfg.critical == 30.5
        assert cfg.hysteresis == 0.8
        assert cfg.debounce_seconds == 90
    finally:
        db.close()

    # Reset thresholds back for subsequent tests
    reset_payload = {
        "warning": 28.0,
        "critical": 32.0,
        "hysteresis": 0.5,
        "debounce_seconds": 60
    }
    client.put("/api/devices/AA:BB:CC:11:22:33/thresholds", json=reset_payload, cookies=admin_cookies)


def test_threshold_config_validation():
    admin_cookies = get_auth_cookies("admin_m4", "adminpass")

    # Invalid: warning > critical
    invalid_payload = {
        "warning": 35.0,
        "critical": 25.0,
        "hysteresis": 0.5,
        "debounce_seconds": 60
    }
    resp = client.put(
        "/api/devices/AA:BB:CC:11:22:33/thresholds",
        json=invalid_payload,
        cookies=admin_cookies
    )
    assert resp.status_code == 400
    assert "warning" in resp.text.lower() or "cannot exceed" in resp.text.lower()

    # Non-existent device
    resp_404 = client.put(
        "/api/devices/AA:BB:CC:99:99:99/thresholds",
        json={"warning": 25.0, "critical": 30.0, "hysteresis": 0.5, "debounce_seconds": 60},
        cookies=admin_cookies
    )
    assert resp_404.status_code == 404


def test_threshold_config_rbac():
    op_cookies = get_auth_cookies("operator_m4", "operatorpass")
    viewer_cookies = get_auth_cookies("viewer_m4", "viewerpass")

    payload = {"warning": 25.0, "critical": 30.0, "hysteresis": 0.5, "debounce_seconds": 60}

    # Operator is forbidden
    resp_op = client.put("/api/devices/AA:BB:CC:11:22:33/thresholds", json=payload, cookies=op_cookies)
    assert resp_op.status_code == 403

    # Viewer is forbidden
    resp_viewer = client.put("/api/devices/AA:BB:CC:11:22:33/thresholds", json=payload, cookies=viewer_cookies)
    assert resp_viewer.status_code == 403

    # Unauthenticated is 401
    client.cookies.clear()
    resp_unauth = client.put("/api/devices/AA:BB:CC:11:22:33/thresholds", json=payload)
    assert resp_unauth.status_code == 401


# ==========================================
# 2. INGEST THRESHOLD EVALUATION (Tasks 4.2 - 4.4, 11.2)
# ==========================================

def test_temperature_normal_no_alert():
    db = SessionLocal()
    try:
        db.query(event_log).delete()
        db.commit()
    finally:
        db.close()

    # Normal reading (25.0°C < warning 28.0°C)
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 25.0,
        "HUMID": 50.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:11:22:33").all()
        assert len(events) == 0
    finally:
        db.close()


def test_temperature_warning_alert():
    # Warning breach: 29.5°C >= warning 28.0°C and < critical 32.0°C
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 29.5,
        "HUMID": 55.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:11:22:33").all()
        assert len(events) == 1
        ev = events[0]
        assert ev.severity == "warning"
        assert ev.metric == "temperature"
        assert ev.alarm == "TEMP_WARNING"
        assert ev.value == 29.5
        assert ev.threshold == 28.0
        assert ev.room_id == "room_server_m4"
        assert ev.resolved_at is None
    finally:
        db.close()


def test_debounce_suppression_warning():
    # Another warning reading immediately after (within 60s debounce window)
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 30.0,
        "HUMID": 56.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:11:22:33").all()
        # Should still be exactly 1 event because debounce suppressed duplicate warning
        assert len(events) == 1
    finally:
        db.close()


def test_escalation_from_warning_to_critical():
    # Critical breach (33.0°C >= critical 32.0°C) within debounce window:
    # Must NOT be suppressed because severity escalated!
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 33.0,
        "HUMID": 60.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = (
            db.query(event_log)
            .filter(event_log.dev_id == "AA:BB:CC:11:22:33")
            .order_by(event_log.timestamp.asc())
            .all()
        )
        assert len(events) == 2
        crit_ev = events[1]
        assert crit_ev.severity == "critical"
        assert crit_ev.metric == "temperature"
        assert crit_ev.alarm == "TEMP_CRITICAL"
        assert crit_ev.value == 33.0
        assert crit_ev.threshold == 32.0
        assert crit_ev.resolved_at is None
    finally:
        db.close()


def test_debounce_suppression_critical():
    # Another critical reading immediately after (within 60s debounce window)
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 34.0,
        "HUMID": 62.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:11:22:33").all()
        # Still 2 events (duplicate critical suppressed)
        assert len(events) == 2
    finally:
        db.close()


def test_hysteresis_deadband():
    # Temperature drops to 27.8°C:
    # 27.8°C < warning (28.0°C), BUT >= (warning - hysteresis = 27.5°C)
    # The deadband prevents resolution.
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 27.8,
        "HUMID": 50.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        open_events = (
            db.query(event_log)
            .filter(
                event_log.dev_id == "AA:BB:CC:11:22:33",
                event_log.resolved_at.is_(None)
            )
            .all()
        )
        # Open events remain unresolved while in deadband
        assert len(open_events) == 2
    finally:
        db.close()


def test_hysteresis_recovery_resolution():
    # Temperature drops below recovery threshold (27.2°C < 27.5°C):
    # All open temperature alerts for AA:BB:CC:11:22:33 must be marked resolved!
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:11:22:33",
        "DEV_NAME": "Temp Sensor Server",
        "DEV_TYPE": "TS",
        "TEMP": 27.2,
        "HUMID": 48.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:11:22:33").all()
        assert len(events) == 2
        for ev in events:
            assert ev.resolved_at is not None, f"Event {ev.event_id} should be resolved"
    finally:
        db.close()


def test_ats_emergency_evaluation_and_resolution():
    # 1. Ingest ATS with EMERGENCY = True
    ats_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:44:55:66",
        "DEV_NAME": "ATS Generator Unit",
        "DEV_TYPE": "ATS",
        "STATE": "EMERGENCY_ACTIVE",
        "PLN": 0.0,
        "GENSET": 220.0,
        "AKI": 12.8,
        "REM_HOUR": 10.0,
        "REM_MIN": 0.0,
        "REM_SEC": 0.0,
        "AUTO_MODE": True,
        "EMERGENCY": True
    }
    resp = client.post("/api/iot", json=ats_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        ats_events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:44:55:66").all()
        assert len(ats_events) == 1
        ev = ats_events[0]
        assert ev.metric == "emergency"
        assert ev.severity == "critical"
        assert ev.alarm == "ATS_EMERGENCY"
        assert ev.resolved_at is None
    finally:
        db.close()

    # 2. Duplicate emergency within debounce window is suppressed
    resp2 = client.post("/api/iot", json=ats_payload, headers=get_hub_headers())
    assert resp2.status_code == 200
    db = SessionLocal()
    try:
        ats_events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:44:55:66").all()
        assert len(ats_events) == 1
    finally:
        db.close()

    # 3. Emergency cleared (EMERGENCY = False) -> resolves open emergency alert
    ats_cleared = dict(ats_payload)
    ats_cleared["EMERGENCY"] = False
    ats_cleared["STATE"] = "PLN_NORMAL"
    resp3 = client.post("/api/iot", json=ats_cleared, headers=get_hub_headers())
    assert resp3.status_code == 200

    db = SessionLocal()
    try:
        ats_events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:44:55:66").all()
        assert len(ats_events) == 1
        assert ats_events[0].resolved_at is not None
    finally:
        db.close()


def test_default_threshold_fallback():
    # dev_nodefault has no custom threshold config; default warning is 28.0, critical 32.0, hysteresis 0.5
    ts_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:77:88:99",
        "DEV_NAME": "Temp Sensor Default Thresh",
        "DEV_TYPE": "TS",
        "TEMP": 29.0,
        "HUMID": 50.0
    }
    resp = client.post("/api/iot", json=ts_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:77:88:99").all()
        assert len(events) == 1
        assert events[0].severity == "warning"
        assert events[0].threshold == 28.0
        assert events[0].resolved_at is None
    finally:
        db.close()


# ==========================================
# 3. GET /api/alerts ENDPOINT (Task 4.5)
# ==========================================

def test_get_alerts_rbac():
    # Unauthenticated
    client.cookies.clear()
    resp_unauth = client.get("/api/alerts")
    assert resp_unauth.status_code == 401

    # Authenticated (Viewer, Operator, Admin)
    for role_user in [("viewer_m4", "viewerpass"), ("operator_m4", "operatorpass"), ("admin_m4", "adminpass")]:
        cookies = get_auth_cookies(role_user[0], role_user[1])
        resp = client.get("/api/alerts", cookies=cookies)
        assert resp.status_code == 200, f"Role {role_user[0]} failed to access /api/alerts"
        data = resp.json()
        assert "total" in data
        assert "alerts" in data
        assert isinstance(data["alerts"], list)


def test_get_alerts_filtering_and_pagination():
    cookies = get_auth_cookies("admin_m4", "adminpass")

    # 1. Total count without filters
    resp_all = client.get("/api/alerts", cookies=cookies)
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["total"] >= 3  # We logged TS server, ATS, and TS default events

    # 2. Filter by severity = "warning"
    resp_warn = client.get("/api/alerts?severity=warning", cookies=cookies)
    assert resp_warn.status_code == 200
    data_warn = resp_warn.json()
    for a in data_warn["alerts"]:
        assert a["severity"] == "warning"

    # 3. Filter by severity = "critical"
    resp_crit = client.get("/api/alerts?severity=critical", cookies=cookies)
    assert resp_crit.status_code == 200
    data_crit = resp_crit.json()
    for a in data_crit["alerts"]:
        assert a["severity"] == "critical"

    # 4. Invalid severity
    resp_invalid_sev = client.get("/api/alerts?severity=unknown", cookies=cookies)
    assert resp_invalid_sev.status_code == 400

    # 5. Filter by status = "open"
    resp_open = client.get("/api/alerts?status=open", cookies=cookies)
    assert resp_open.status_code == 200
    data_open = resp_open.json()
    for a in data_open["alerts"]:
        assert a["resolved_at"] is None

    # 6. Filter by status = "resolved"
    resp_res = client.get("/api/alerts?status=resolved", cookies=cookies)
    assert resp_res.status_code == 200
    data_res = resp_res.json()
    for a in data_res["alerts"]:
        assert a["resolved_at"] is not None

    # 7. Invalid status
    resp_invalid_st = client.get("/api/alerts?status=invalid_status", cookies=cookies)
    assert resp_invalid_st.status_code == 400

    # 8. Filter by room
    resp_room = client.get("/api/alerts?rooms=room_gen_m4", cookies=cookies)
    assert resp_room.status_code == 200
    data_room = resp_room.json()
    for a in data_room["alerts"]:
        assert a["room_id"] == "room_gen_m4"
        assert a["room_name"] == "Generator Room M4"

    # 9. Filter by device
    resp_dev = client.get("/api/alerts?devices=AA:BB:CC:11:22:33", cookies=cookies)
    assert resp_dev.status_code == 200
    data_dev = resp_dev.json()
    for a in data_dev["alerts"]:
        assert a["dev_id"] == "AA:BB:CC:11:22:33"
        assert a["dev_name"] == "Temp Sensor Server"

    # 10. Pagination (limit and offset)
    resp_paged = client.get("/api/alerts?limit=1&offset=0", cookies=cookies)
    assert resp_paged.status_code == 200
    data_paged = resp_paged.json()
    assert len(data_paged["alerts"]) == 1
    assert data_paged["total"] == data_all["total"]

    # 11. Time range filter
    now = datetime.now(UTC)
    t_past = (now - timedelta(hours=2)).isoformat()
    t_future = (now + timedelta(hours=2)).isoformat()
    resp_timerange = client.get(f"/api/alerts?start_time={t_past}&end_time={t_future}", cookies=cookies)
    assert resp_timerange.status_code == 200
    assert resp_timerange.json()["total"] == data_all["total"]

    # Time range in the distant past returns 0
    t_ancient_start = (now - timedelta(days=10)).isoformat()
    t_ancient_end = (now - timedelta(days=9)).isoformat()
    resp_empty = client.get(f"/api/alerts?start_time={t_ancient_start}&end_time={t_ancient_end}", cookies=cookies)
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total"] == 0


def test_ac_device_temperature_evaluation():
    # AC device reporting TEMP
    db = SessionLocal()
    try:
        dev_ac = dev_table(
            dev_id="AA:BB:CC:AC:01:01",
            dev_name="AC Server Room",
            dev_type="AC",
            hub_id=TEST_HUB_ID,
            room_id="room_server_m4",
            is_active=True,
            created_at=datetime.now(UTC)
        )
        db.add(dev_ac)
        db.commit()
    finally:
        db.close()

    ac_payload = {
        "HUB_NAME": TEST_HUB_ID,
        "DEV_ID": "AA:BB:CC:AC:01:01",
        "DEV_NAME": "AC Server Room",
        "DEV_TYPE": "AC",
        "AC1_POWER": "ON",
        "AC1_TEMP": 24.0,
        "AC2_POWER": "OFF",
        "AC2_TEMP": 26.0,
        "TEMP": 33.5,  # Exceeds default critical 32.0
        "HUMID": 60.0
    }
    resp = client.post("/api/iot", json=ac_payload, headers=get_hub_headers())
    assert resp.status_code == 200

    db = SessionLocal()
    try:
        events = db.query(event_log).filter(event_log.dev_id == "AA:BB:CC:AC:01:01").all()
        assert len(events) == 1
        assert events[0].severity == "critical"
        assert events[0].alarm == "TEMP_CRITICAL"
        assert events[0].value == 33.5
    finally:
        db.close()

