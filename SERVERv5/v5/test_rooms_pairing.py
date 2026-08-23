# test_rooms_pairing.py
# Test Suite for Milestone 2: Rooms & Device Pairing Backend API in HubGate V5

import os
import sys
import uuid
import datetime
from datetime import UTC
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
    rooms, device_threshold_config, temperature_data, ats_data, data_table
)
from auth import hash_password
from hubgatev5 import api

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        # Clear tables for clean module isolation
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

        # Create test users with argon2id hashed passwords
        admin = User(
            id="user-admin-m2",
            username="admin_m2",
            password_hash=hash_password("adminpass"),
            display_name="Admin M2",
            role="admin"
        )
        operator = User(
            id="user-operator-m2",
            username="operator_m2",
            password_hash=hash_password("operatorpass"),
            display_name="Operator M2",
            role="operator"
        )
        viewer = User(
            id="user-viewer-m2",
            username="viewer_m2",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer M2",
            role="viewer"
        )
        db.add_all([admin, operator, viewer])

        # Create default test hub
        hub = hub_table(
            hub_id="HUB_TEST_M2",
            hub_name="Edge Hub Test M2",
            hub_key="secret_key_m2",
            is_active=True
        )
        db.add(hub)

        db.commit()
    finally:
        db.close()


def get_auth_cookies(username: str, password: str) -> dict:
    """Helper to log in and retrieve session cookie."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


# ==========================================
# 1. ROOM CRUD TESTS
# ==========================================

def test_room_crud_admin():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # A. Create Room
    create_payload = {
        "name": "Server Room A",
        "hub_id": "HUB_TEST_M2",
        "floor_plan_image_path": "/static/plans/room_a.png"
    }
    resp = client.post("/api/rooms", json=create_payload, cookies=admin_cookies)
    assert resp.status_code == 201, f"Failed to create room: {resp.text}"
    room_data = resp.json()
    assert room_data["name"] == "Server Room A"
    assert room_data["hub_id"] == "HUB_TEST_M2"
    assert room_data["floor_plan_image_path"] == "/static/plans/room_a.png"
    assert room_data["device_count"] == 0
    assert "id" in room_data
    room_id = room_data["id"]

    # B. Prevent Duplicate Room Name (400 Bad Request)
    resp_dup = client.post("/api/rooms", json={"name": "Server Room A"}, cookies=admin_cookies)
    assert resp_dup.status_code == 400
    assert "already exists" in resp_dup.json()["detail"]

    # C. List Rooms
    resp_list = client.get("/api/rooms", cookies=admin_cookies)
    assert resp_list.status_code == 200
    rooms_list = resp_list.json()
    assert len(rooms_list) >= 1
    found = next((r for r in rooms_list if r["id"] == room_id), None)
    assert found is not None
    assert found["name"] == "Server Room A"

    # D. Update Room (PATCH)
    patch_payload = {
        "name": "Server Room A Modified",
        "floor_plan_image_path": "/static/plans/room_a_v2.png"
    }
    resp_patch = client.patch(f"/api/rooms/{room_id}", json=patch_payload, cookies=admin_cookies)
    assert resp_patch.status_code == 200
    updated = resp_patch.json()
    assert updated["name"] == "Server Room A Modified"
    assert updated["floor_plan_image_path"] == "/static/plans/room_a_v2.png"

    # Update non-existent room -> 404
    resp_patch_404 = client.patch("/api/rooms/non_existent_room_id", json={"name": "X"}, cookies=admin_cookies)
    assert resp_patch_404.status_code == 404

    # E. Delete Room (Empty)
    resp_del = client.delete(f"/api/rooms/{room_id}", cookies=admin_cookies)
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # Verify deleted
    resp_list_after = client.get("/api/rooms", cookies=admin_cookies)
    found_after = next((r for r in resp_list_after.json() if r["id"] == room_id), None)
    assert found_after is None


# ==========================================
# 2. DELETION REJECTION WITH ASSIGNED DEVICES
# ==========================================

def test_room_deletion_rejection_with_assigned_devices():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # 1. Create Room
    resp = client.post("/api/rooms", json={"name": "Battery Room B"}, cookies=admin_cookies)
    assert resp.status_code == 201
    room_id = resp.json()["id"]

    # 2. Seed a device into database
    db = SessionLocal()
    try:
        dev = dev_table(
            dev_id="MAC_ROOM_DEL_01",
            dev_name="Battery Monitor 1",
            dev_type="ATS",
            hub_id="HUB_TEST_M2",
            is_active=False
        )
        db.add(dev)
        db.commit()
    finally:
        db.close()

    # 3. Pair device to the room
    pair_payload = {
        "dev_name": "Battery Monitor 1",
        "room_id": room_id,
        "marker_x": 20.0,
        "marker_y": 30.0
    }
    resp_pair = client.post("/api/devices/MAC_ROOM_DEL_01/pair", json=pair_payload, cookies=admin_cookies)
    assert resp_pair.status_code == 200

    # 4. Verify room device_count is 1
    resp_rooms = client.get("/api/rooms", cookies=admin_cookies)
    target_room = next((r for r in resp_rooms.json() if r["id"] == room_id), None)
    assert target_room is not None
    assert target_room["device_count"] == 1

    # 5. Attempt deleting room with assigned device -> 400 Bad Request
    resp_del_fail = client.delete(f"/api/rooms/{room_id}", cookies=admin_cookies)
    assert resp_del_fail.status_code == 400
    assert "Cannot delete room with assigned devices" in resp_del_fail.json()["detail"]

    # 6. Unpair the device
    resp_unpair = client.post("/api/devices/MAC_ROOM_DEL_01/unpair", cookies=admin_cookies)
    assert resp_unpair.status_code == 200

    # 7. Now room deletion should succeed
    resp_del_ok = client.delete(f"/api/rooms/{room_id}", cookies=admin_cookies)
    assert resp_del_ok.status_code == 200
    assert resp_del_ok.json()["status"] == "deleted"


# ==========================================
# 3. ROLE-BASED ACCESS CONTROL (RBAC)
# ==========================================

def test_rbac_protection():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")
    operator_cookies = get_auth_cookies("operator_m2", "operatorpass")
    viewer_cookies = get_auth_cookies("viewer_m2", "viewerpass")

    # Create a room as admin for test targets
    resp_room = client.post("/api/rooms", json={"name": "RBAC Test Room"}, cookies=admin_cookies)
    room_id = resp_room.json()["id"]

    # Seed a device
    db = SessionLocal()
    try:
        dev = dev_table(dev_id="MAC_RBAC_DEV_01", dev_name="RBAC Dev", dev_type="TS", hub_id="HUB_TEST_M2", is_active=False)
        db.add(dev)
        db.commit()
    finally:
        db.close()

    # A. Unauthenticated tests -> 401
    client.cookies.clear()
    assert client.get("/api/rooms").status_code == 401
    assert client.post("/api/rooms", json={"name": "No Auth"}).status_code == 401
    assert client.patch(f"/api/rooms/{room_id}", json={"name": "No Auth"}).status_code == 401
    assert client.delete(f"/api/rooms/{room_id}").status_code == 401
    assert client.post("/api/gateways/HUB_TEST_M2/room", json={"room_id": room_id}).status_code == 401
    assert client.post("/api/devices/MAC_RBAC_DEV_01/pair", json={"dev_name": "D", "room_id": room_id}).status_code == 401
    assert client.post("/api/devices/MAC_RBAC_DEV_01/unpair").status_code == 401
    assert client.get("/api/devices").status_code == 401

    # B. Viewer role: Can read rooms and devices, cannot perform admin write operations
    assert client.get("/api/rooms", cookies=viewer_cookies).status_code == 200
    assert client.get("/api/devices", cookies=viewer_cookies).status_code == 200
    assert client.post("/api/rooms", json={"name": "V Room"}, cookies=viewer_cookies).status_code == 403
    assert client.patch(f"/api/rooms/{room_id}", json={"name": "V Edit"}, cookies=viewer_cookies).status_code == 403
    assert client.delete(f"/api/rooms/{room_id}", cookies=viewer_cookies).status_code == 403
    assert client.post("/api/gateways/HUB_TEST_M2/room", json={"room_id": room_id}, cookies=viewer_cookies).status_code == 403
    assert client.post("/api/devices/MAC_RBAC_DEV_01/pair", json={"dev_name": "D", "room_id": room_id}, cookies=viewer_cookies).status_code == 403
    assert client.post("/api/devices/MAC_RBAC_DEV_01/unpair", cookies=viewer_cookies).status_code == 403

    # C. Operator role: Can read rooms and devices, cannot perform admin room/pairing operations
    assert client.get("/api/rooms", cookies=operator_cookies).status_code == 200
    assert client.get("/api/devices", cookies=operator_cookies).status_code == 200
    assert client.post("/api/rooms", json={"name": "Op Room"}, cookies=operator_cookies).status_code == 403
    assert client.patch(f"/api/rooms/{room_id}", json={"name": "Op Edit"}, cookies=operator_cookies).status_code == 403
    assert client.delete(f"/api/rooms/{room_id}", cookies=operator_cookies).status_code == 403
    assert client.post("/api/gateways/HUB_TEST_M2/room", json={"room_id": room_id}, cookies=operator_cookies).status_code == 403
    assert client.post("/api/devices/MAC_RBAC_DEV_01/pair", json={"dev_name": "D", "room_id": room_id}, cookies=operator_cookies).status_code == 403
    assert client.post("/api/devices/MAC_RBAC_DEV_01/unpair", cookies=operator_cookies).status_code == 403

    # Clean up
    client.delete(f"/api/rooms/{room_id}", cookies=admin_cookies)


# ==========================================
# 4. GATEWAY - ROOM ASSOCIATION
# ==========================================

def test_gateway_room_association():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # Create room
    resp = client.post("/api/rooms", json={"name": "Gateway Station 1"}, cookies=admin_cookies)
    assert resp.status_code == 201
    room_id = resp.json()["id"]

    # Associate gateway
    payload = {"room_id": room_id}
    resp_assign = client.post("/api/gateways/HUB_TEST_M2/room", json=payload, cookies=admin_cookies)
    assert resp_assign.status_code == 200
    assert resp_assign.json()["status"] == "assigned"
    assert resp_assign.json()["hub_id"] == "HUB_TEST_M2"
    assert resp_assign.json()["room_id"] == room_id

    # Verify DB state
    db = SessionLocal()
    try:
        hub = db.get(hub_table, "HUB_TEST_M2")
        room = db.get(rooms, room_id)
        assert hub.room == "Gateway Station 1"
        assert room.hub_id == "HUB_TEST_M2"
    finally:
        db.close()

    # Invalid hub_id -> 404
    resp_bad_hub = client.post("/api/gateways/NON_EXISTENT_HUB/room", json=payload, cookies=admin_cookies)
    assert resp_bad_hub.status_code == 404

    # Invalid room_id -> 404
    resp_bad_room = client.post("/api/gateways/HUB_TEST_M2/room", json={"room_id": "non_existent_room"}, cookies=admin_cookies)
    assert resp_bad_room.status_code == 404


# ==========================================
# 5. DEVICE PAIRING LIFECYCLE
# ==========================================

def test_device_pairing_lifecycle():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # Create room
    resp_r = client.post("/api/rooms", json={"name": "HVAC Control Zone"}, cookies=admin_cookies)
    room_id = resp_r.json()["id"]

    # Seed pending device
    db = SessionLocal()
    try:
        dev = dev_table(
            dev_id="MAC_PAIR_001",
            dev_name="Pending Temp Sensor",
            dev_type="TS",
            hub_id="HUB_TEST_M2",
            is_active=False
        )
        db.add(dev)
        db.commit()
    finally:
        db.close()

    # Pair device
    pair_body = {
        "dev_name": "HVAC Room Temp 1",
        "room_id": room_id,
        "marker_x": 55.4,
        "marker_y": 80.2,
        "warning_threshold": 28.5,
        "critical_threshold": 35.0,
        "hysteresis": 0.8,
        "debounce_seconds": 90
    }
    resp_pair = client.post("/api/devices/MAC_PAIR_001/pair", json=pair_body, cookies=admin_cookies)
    assert resp_pair.status_code == 200, f"Pairing failed: {resp_pair.text}"
    data = resp_pair.json()

    assert data["dev_id"] == "MAC_PAIR_001"
    assert data["dev_name"] == "HVAC Room Temp 1"
    assert data["room_id"] == room_id
    assert data["marker_x"] == 55.4
    assert data["marker_y"] == 80.2
    assert data["is_active"] is True
    assert data["threshold_config"] is not None
    assert data["threshold_config"]["warning"] == 28.5
    assert data["threshold_config"]["critical"] == 35.0
    assert data["threshold_config"]["hysteresis"] == 0.8
    assert data["threshold_config"]["debounce_seconds"] == 90

    # Verify DB directly
    db = SessionLocal()
    try:
        queried_dev = db.get(dev_table, "MAC_PAIR_001")
        assert queried_dev.is_active is True
        assert queried_dev.dev_name == "HVAC Room Temp 1"
        assert queried_dev.room_id == room_id
        assert queried_dev.threshold_config is not None
        assert queried_dev.threshold_config.warning == 28.5
        assert queried_dev.threshold_config.critical == 35.0
    finally:
        db.close()

    # Pairing to non-existent room -> 404
    resp_bad = client.post(
        "/api/devices/MAC_PAIR_001/pair",
        json={"dev_name": "X", "room_id": "missing_room"},
        cookies=admin_cookies
    )
    assert resp_bad.status_code == 404

    # Pairing non-existent device -> 404
    resp_bad_dev = client.post(
        "/api/devices/MAC_NON_EXISTENT/pair",
        json={"dev_name": "X", "room_id": room_id},
        cookies=admin_cookies
    )
    assert resp_bad_dev.status_code == 404


# ==========================================
# 6. DEVICE UNPAIRING & TELEMETRY PRESERVATION
# ==========================================

def test_device_unpairing_and_telemetry_preservation():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # Create room
    resp_r = client.post("/api/rooms", json={"name": "Telemetry Room"}, cookies=admin_cookies)
    room_id = resp_r.json()["id"]

    # Seed device and historical telemetry
    db = SessionLocal()
    try:
        dev = dev_table(
            dev_id="MAC_HIST_01",
            dev_name="Temp Probe 1",
            dev_type="TS",
            hub_id="HUB_TEST_M2",
            room_id=room_id,
            marker_x=10.0,
            marker_y=20.0,
            is_active=True
        )
        db.add(dev)

        # Add historical telemetry
        t_row = temperature_data(
            data_id="temp_data_001",
            dev_id="MAC_HIST_01",
            timestamp=datetime.datetime.now(UTC),
            temp=24.5,
            humid=55.0
        )
        db.add(t_row)
        db.commit()
    finally:
        db.close()

    # Unpair device
    resp_unpair = client.post("/api/devices/MAC_HIST_01/unpair", cookies=admin_cookies)
    assert resp_unpair.status_code == 200
    assert resp_unpair.json()["status"] == "unpaired"
    assert resp_unpair.json()["is_active"] is False

    # Check DB: device is deactivated and unlinked from room, but telemetry is preserved
    db = SessionLocal()
    try:
        d = db.get(dev_table, "MAC_HIST_01")
        assert d.is_active is False
        assert d.room_id is None
        assert d.marker_x is None
        assert d.marker_y is None

        # Verify historical telemetry remains
        telemetry = db.query(temperature_data).filter(temperature_data.dev_id == "MAC_HIST_01").all()
        assert len(telemetry) == 1
        assert telemetry[0].temp == 24.5
    finally:
        db.close()


# ==========================================
# 7. QUERYING PENDING / ACTIVE / ALL DEVICES
# ==========================================

def test_querying_device_status_filters():
    admin_cookies = get_auth_cookies("admin_m2", "adminpass")

    # Seed active and pending devices
    db = SessionLocal()
    try:
        # Create 2 pending and 2 active
        db.query(dev_table).delete()
        db.commit()

        d_pend1 = dev_table(dev_id="MAC_PEND_1", dev_name="Pending 1", dev_type="TS", hub_id="HUB_TEST_M2", is_active=False)
        d_pend2 = dev_table(dev_id="MAC_PEND_2", dev_name="Pending 2", dev_type="ATS", hub_id="HUB_TEST_M2", is_active=False)
        d_act1 = dev_table(dev_id="MAC_ACT_1", dev_name="Active 1", dev_type="TS", hub_id="HUB_TEST_M2", is_active=True)
        d_act2 = dev_table(dev_id="MAC_ACT_2", dev_name="Active 2", dev_type="AC", hub_id="HUB_TEST_M2", is_active=True)

        db.add_all([d_pend1, d_pend2, d_act1, d_act2])
        db.commit()
    finally:
        db.close()

    # A. Query pending devices
    resp_pend = client.get("/api/devices?status=pending", cookies=admin_cookies)
    assert resp_pend.status_code == 200
    pend_devices = resp_pend.json()
    assert len(pend_devices) == 2
    assert all(d["is_active"] is False for d in pend_devices)
    pend_ids = {d["dev_id"] for d in pend_devices}
    assert pend_ids == {"MAC_PEND_1", "MAC_PEND_2"}

    # B. Query active devices
    resp_act = client.get("/api/devices?status=active", cookies=admin_cookies)
    assert resp_act.status_code == 200
    act_devices = resp_act.json()
    assert len(act_devices) == 2
    assert all(d["is_active"] is True for d in act_devices)
    act_ids = {d["dev_id"] for d in act_devices}
    assert act_ids == {"MAC_ACT_1", "MAC_ACT_2"}

    # C. Query all devices
    resp_all = client.get("/api/devices?status=all", cookies=admin_cookies)
    assert resp_all.status_code == 200
    all_devices = resp_all.json()
    assert len(all_devices) == 4

    # D. Query with invalid status filter -> 400
    resp_bad = client.get("/api/devices?status=unknown", cookies=admin_cookies)
    assert resp_bad.status_code == 400

    # E. Edge Hub Whitelist query (authenticated via headers)
    hub_headers = {"X-Hub-ID": "HUB_TEST_M2", "X-Hub-Key": "secret_key_m2"}
    resp_hub = client.get("/api/devices", headers=hub_headers)
    assert resp_hub.status_code == 200
    hub_devices = resp_hub.json()
    assert len(hub_devices) == 2
    # Verify legacy whitelist schema format: DEV_ID, DEV_NAME, DEV_TYPE, HUB_NAME
    assert "DEV_ID" in hub_devices[0]
    assert "DEV_NAME" in hub_devices[0]
    assert "DEV_TYPE" in hub_devices[0]
    assert "HUB_NAME" in hub_devices[0]
