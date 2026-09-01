# test_phase_a_endpoints.py
# Test Suite for GET /api/devices/{dev_id} and GET /api/commands/{command_id}

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_phase_a.db"

if os.path.exists("./test_phase_a.db"):
    try:
        os.remove("./test_phase_a.db")
    except Exception:
        pass

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, hub_table, dev_table,
    rooms, device_threshold_config, pending_commands
)
from auth import hash_password
from hubgatev5 import api

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        db.query(pending_commands).delete()
        db.query(UserSession).delete()
        db.query(device_threshold_config).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Create test users
        admin = User(
            id="user-admin-phase-a",
            username="admin_phase_a",
            password_hash=hash_password("adminpass"),
            display_name="Admin Phase A",
            role="admin"
        )
        viewer = User(
            id="user-viewer-phase-a",
            username="viewer_phase_a",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer Phase A",
            role="viewer"
        )
        db.add_all([admin, viewer])

        # Create hub
        hub = hub_table(
            hub_id="HUB_PHASE_A",
            hub_name="Phase A Edge Hub",
            hub_key="secret_phase_a",
            is_active=True,
            last_seen=datetime.now(UTC),
        )
        db.add(hub)

        # Create room
        room = rooms(
            id="ROOM_PHASE_A",
            name="Server Room A",
        )
        db.add(room)

        # Create active online device
        dev1 = dev_table(
            dev_id="TS-PHASE-01",
            dev_name="Temp Sensor 01",
            dev_type="TS",
            hub_id="HUB_PHASE_A",
            room_id="ROOM_PHASE_A",
            marker_x=25.0,
            marker_y=50.0,
            is_active=True,
            last_seen=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db.add(dev1)

        # Thresholds for dev1
        thresh1 = device_threshold_config(
            dev_id="TS-PHASE-01",
            warning=28.0,
            critical=32.0,
            hysteresis=0.5,
            debounce_seconds=60,
        )
        db.add(thresh1)

        # Create inactive (pending) device
        dev2 = dev_table(
            dev_id="ATS-PHASE-02",
            dev_name="ATS Sensor 02",
            dev_type="ATS",
            hub_id="HUB_PHASE_A",
            is_active=False,
            last_seen=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        db.add(dev2)

        # Create offline device (last_seen > 25s ago)
        dev3 = dev_table(
            dev_id="AC-PHASE-03",
            dev_name="AC Node 03",
            dev_type="AC",
            hub_id="HUB_PHASE_A",
            is_active=True,
            last_seen=datetime.now(UTC) - timedelta(seconds=120),
            created_at=datetime.now(UTC),
        )
        db.add(dev3)

        # Create pending command
        cmd1 = pending_commands(
            command_id="cmd-test-111",
            dev_id="TS-PHASE-01",
            hub_id="HUB_PHASE_A",
            payload={"action": "reboot"},
            status="pending",
            created_at=datetime.now(UTC),
        )
        # Create delivered command
        cmd2 = pending_commands(
            command_id="cmd-test-222",
            dev_id="TS-PHASE-01",
            hub_id="HUB_PHASE_A",
            payload={"target": "AC1", "action": "ON"},
            status="delivered",
            created_at=datetime.now(UTC) - timedelta(minutes=5),
            delivered_at=datetime.now(UTC) - timedelta(minutes=4),
        )
        # Create orphaned command pointing to nonexistent device
        cmd_orphan = pending_commands(
            command_id="cmd-orphan-999",
            dev_id="NONEXISTENT-DEV",
            hub_id="HUB_PHASE_A",
            payload={"action": "ping"},
            status="pending",
            created_at=datetime.now(UTC),
        )
        db.add_all([cmd1, cmd2, cmd_orphan])

        db.commit()
    finally:
        db.close()


def get_auth_cookies(username: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


# ==========================================
# 1. GET /api/devices/{dev_id} Tests
# ==========================================

def test_get_device_unauthenticated():
    client.cookies.clear()
    resp = client.get("/api/devices/TS-PHASE-01")
    assert resp.status_code == 401


def test_get_device_success_online_with_thresholds():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/devices/TS-PHASE-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dev_id"] == "TS-PHASE-01"
    assert data["dev_name"] == "Temp Sensor 01"
    assert data["dev_type"] == "TS"
    assert data["hub_id"] == "HUB_PHASE_A"
    assert data["room_id"] == "ROOM_PHASE_A"
    assert data["is_active"] is True
    assert data["status"] == "online"
    assert data["marker_x"] == 25.0
    assert data["marker_y"] == 50.0
    assert data["threshold_config"] is not None
    assert data["threshold_config"]["warning"] == 28.0
    assert data["threshold_config"]["critical"] == 32.0
    assert data["threshold_config"]["hysteresis"] == 0.5
    assert data["threshold_config"]["debounce_seconds"] == 60


def test_get_device_pending_status():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/devices/ATS-PHASE-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dev_id"] == "ATS-PHASE-02"
    assert data["is_active"] is False
    assert data["status"] == "pending"
    assert data["threshold_config"] is None


def test_get_device_offline_status():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/devices/AC-PHASE-03")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dev_id"] == "AC-PHASE-03"
    assert data["is_active"] is True
    assert data["status"] == "offline"


def test_get_device_not_found():
    cookies = get_auth_cookies("admin_phase_a", "adminpass")
    client.cookies.update(cookies)
    resp = client.get("/api/devices/NONEXISTENT_DEVICE")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ==========================================
# 2. GET /api/commands/{command_id} Tests
# ==========================================

def test_get_command_unauthenticated():
    client.cookies.clear()
    resp = client.get("/api/commands/cmd-test-111")
    assert resp.status_code == 401


def test_get_command_status_pending():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/commands/cmd-test-111")
    assert resp.status_code == 200
    data = resp.json()
    assert data["command_id"] == "cmd-test-111"
    assert data["dev_id"] == "TS-PHASE-01"
    assert data["hub_id"] == "HUB_PHASE_A"
    assert data["status"] == "pending"
    assert data["payload"] == {"action": "reboot"}
    assert data["created_at"] is not None
    assert data["delivered_at"] is None


def test_get_command_status_delivered():
    cookies = get_auth_cookies("admin_phase_a", "adminpass")
    client.cookies.update(cookies)
    resp = client.get("/api/commands/cmd-test-222")
    assert resp.status_code == 200
    data = resp.json()
    assert data["command_id"] == "cmd-test-222"
    assert data["status"] == "delivered"
    assert data["payload"] == {"target": "AC1", "action": "ON"}
    assert data["delivered_at"] is not None


def test_get_command_not_found():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/commands/non-existent-cmd-id")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_command_orphaned_device_not_found():
    cookies = get_auth_cookies("viewer_phase_a", "viewerpass")
    client.cookies.update(cookies)
    resp = client.get("/api/commands/cmd-orphan-999")
    assert resp.status_code == 404
