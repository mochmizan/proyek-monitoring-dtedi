# test_floor_plan_map.py
# Test Suite for Milestone 3: Floor Plan & Map Backend API in HubGate V5

import io
import os
import sys
import uuid
from datetime import UTC, datetime
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
from app.main import api
from app.routers.rooms import resolve_static_disk_path
from app.core.config import FLOORPLAN_UPLOAD_DIR

client = TestClient(api)
api.state.limiter.enabled = False


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    initial_files = set(os.listdir(FLOORPLAN_UPLOAD_DIR)) if os.path.exists(FLOORPLAN_UPLOAD_DIR) else set()
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
            id="user-admin-m3",
            username="admin_m3",
            password_hash=hash_password("adminpass"),
            display_name="Admin M3",
            role="admin"
        )
        operator = User(
            id="user-operator-m3",
            username="operator_m3",
            password_hash=hash_password("operatorpass"),
            display_name="Operator M3",
            role="operator"
        )
        viewer = User(
            id="user-viewer-m3",
            username="viewer_m3",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer M3",
            role="viewer"
        )
        db.add_all([admin, operator, viewer])

        # Create default test hub
        hub = hub_table(
            hub_id="HUB_TEST_M3",
            hub_name="Edge Hub Test M3",
            hub_key="secret_key_m3",
            is_active=True
        )
        db.add(hub)
        db.commit()
    finally:
        db.close()

    yield

    # Clean up uploaded floorplan files created during testing
    if os.path.exists(FLOORPLAN_UPLOAD_DIR):
        for fname in os.listdir(FLOORPLAN_UPLOAD_DIR):
            if fname not in initial_files:
                fpath = os.path.join(FLOORPLAN_UPLOAD_DIR, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except OSError:
                    pass



def get_auth_cookies(username: str, password: str) -> dict:
    """Helper to log in and retrieve session cookie."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


# Minimal valid PNG file bytes for testing (1x1 transparent PNG)
DUMMY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid JPEG header / bytes for testing
DUMMY_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"

# Minimal valid SVG content
DUMMY_SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="red"/></svg>'


# ==========================================
# 1. FLOOR PLAN UPLOAD TESTS
# ==========================================

def test_upload_floor_plan_admin_success():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    # 1. Create a test room
    create_resp = client.post(
        "/api/rooms",
        json={"name": "Server Room Alpha"},
        cookies=admin_cookies
    )
    assert create_resp.status_code == 201
    room_id = create_resp.json()["id"]

    # 2. Upload PNG floor plan
    files = {
        "file": ("floorplan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")
    }
    upload_resp = client.post(
        f"/api/rooms/{room_id}/floor-plan",
        files=files,
        cookies=admin_cookies
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["room_id"] == room_id
    assert data["floor_plan_url"].startswith("/static/uploads/floorplans/")
    assert data["floor_plan_url"].endswith(".png")
    assert "successfully" in data["message"].lower()

    # 3. Verify file exists on local disk
    disk_path = resolve_static_disk_path(data["floor_plan_url"])
    assert os.path.exists(disk_path)
    assert os.path.isfile(disk_path)
    with open(disk_path, "rb") as f:
        assert f.read() == DUMMY_PNG_BYTES

    # 4. Verify static file serving endpoint
    static_resp = client.get(data["floor_plan_url"])
    assert static_resp.status_code == 200
    assert static_resp.content == DUMMY_PNG_BYTES

    # 5. Verify room in DB has updated floor_plan_image_path
    db = SessionLocal()
    try:
        room = db.get(rooms, room_id)
        assert room.floor_plan_image_path == data["floor_plan_url"]
    finally:
        db.close()


def test_upload_floor_plan_rbac_forbidden():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")
    operator_cookies = get_auth_cookies("operator_m3", "operatorpass")
    viewer_cookies = get_auth_cookies("viewer_m3", "viewerpass")

    # Create test room
    create_resp = client.post(
        "/api/rooms",
        json={"name": "RBAC Floorplan Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    files = {
        "file": ("floorplan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")
    }

    # A. Unauthenticated -> 401
    client.cookies.clear()
    resp_unauth = client.post(f"/api/rooms/{room_id}/floor-plan", files=files)
    assert resp_unauth.status_code == 401

    # B. Viewer -> 403
    files_v = {"file": ("floorplan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
    resp_viewer = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_v, cookies=viewer_cookies)
    assert resp_viewer.status_code == 403

    # C. Operator -> 403
    files_op = {"file": ("floorplan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
    resp_op = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_op, cookies=operator_cookies)
    assert resp_op.status_code == 403


def test_upload_floor_plan_invalid_file_type():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    create_resp = client.post(
        "/api/rooms",
        json={"name": "Invalid File Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 1. Text file
    files_txt = {"file": ("notes.txt", io.BytesIO(b"Not an image"), "text/plain")}
    resp_txt = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_txt, cookies=admin_cookies)
    assert resp_txt.status_code == 400
    assert "invalid file type" in resp_txt.json()["detail"].lower()

    # 2. Executable
    files_exe = {"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-msdownload")}
    resp_exe = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_exe, cookies=admin_cookies)
    assert resp_exe.status_code == 400
    assert "invalid file type" in resp_exe.json()["detail"].lower()

    # 3. Python script
    files_py = {"file": ("script.py", io.BytesIO(b"print('hello')"), "text/x-python")}
    resp_py = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_py, cookies=admin_cookies)
    assert resp_py.status_code == 400


def test_upload_floor_plan_validation_errors():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    create_resp = client.post(
        "/api/rooms",
        json={"name": "Validation Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 1. Empty file
    files_empty = {"file": ("empty.png", io.BytesIO(b""), "image/png")}
    resp_empty = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_empty, cookies=admin_cookies)
    assert resp_empty.status_code == 400
    assert "empty" in resp_empty.json()["detail"].lower()

    # 2. File exceeding 5MB
    large_payload = b"0" * (5 * 1024 * 1024 + 10)
    files_large = {"file": ("large.png", io.BytesIO(large_payload), "image/png")}
    resp_large = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_large, cookies=admin_cookies)
    assert resp_large.status_code == 400
    assert "limit" in resp_large.json()["detail"].lower() or "5mb" in resp_large.json()["detail"].lower()

    # 3. Non-existent room
    files_valid = {"file": ("floorplan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
    resp_404 = client.post("/api/rooms/non_existent_room_999/floor-plan", files=files_valid, cookies=admin_cookies)
    assert resp_404.status_code == 404


def test_upload_floor_plan_replace_existing():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    # 1. Create Room
    create_resp = client.post(
        "/api/rooms",
        json={"name": "Replace Floorplan Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 2. Upload first floor plan (PNG)
    files_1 = {"file": ("first_plan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
    resp_1 = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_1, cookies=admin_cookies)
    assert resp_1.status_code == 200
    url_1 = resp_1.json()["floor_plan_url"]
    disk_path_1 = resolve_static_disk_path(url_1)
    assert os.path.exists(disk_path_1)

    # 3. Replace with second floor plan (SVG)
    files_2 = {"file": ("second_plan.svg", io.BytesIO(DUMMY_SVG_BYTES), "image/svg+xml")}
    resp_2 = client.post(f"/api/rooms/{room_id}/floor-plan", files=files_2, cookies=admin_cookies)
    assert resp_2.status_code == 200
    url_2 = resp_2.json()["floor_plan_url"]
    disk_path_2 = resolve_static_disk_path(url_2)

    # 4. Verify old file was deleted from disk
    assert not os.path.exists(disk_path_1), "Old floor plan file was not deleted from disk!"

    # 5. Verify new file exists and is accessible
    assert os.path.exists(disk_path_2)
    assert disk_path_1 != disk_path_2
    with open(disk_path_2, "rb") as f:
        assert f.read() == DUMMY_SVG_BYTES


# ==========================================
# 2. ROOM MAP ENDPOINT TESTS
# ==========================================

def test_get_room_map_with_image_and_devices():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")
    operator_cookies = get_auth_cookies("operator_m3", "operatorpass")
    viewer_cookies = get_auth_cookies("viewer_m3", "viewerpass")

    # 1. Create room
    create_resp = client.post(
        "/api/rooms",
        json={"name": "Facility Control Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 2. Upload floor plan image
    files = {"file": ("facility.jpg", io.BytesIO(DUMMY_JPEG_BYTES), "image/jpeg")}
    upload_resp = client.post(f"/api/rooms/{room_id}/floor-plan", files=files, cookies=admin_cookies)
    assert upload_resp.status_code == 200
    floor_plan_url = upload_resp.json()["floor_plan_url"]

    # 3. Create devices in DB and pair to room
    db = SessionLocal()
    try:
        # TS Device
        dev_ts = dev_table(
            dev_id="DEV_MAP_TS_01",
            dev_name="Temperature Sensor A",
            dev_type="TS",
            hub_id="HUB_TEST_M3",
            is_active=True,
            room_id=room_id,
            marker_x=15.5,
            marker_y=30.0,
            created_at=datetime.now(UTC)
        )
        # ATS Device
        dev_ats = dev_table(
            dev_id="DEV_MAP_ATS_01",
            dev_name="Main Generator ATS",
            dev_type="ATS",
            hub_id="HUB_TEST_M3",
            is_active=True,
            room_id=room_id,
            marker_x=80.0,
            marker_y=75.5,
            created_at=datetime.now(UTC)
        )
        # Inactive Device
        dev_inactive = dev_table(
            dev_id="DEV_MAP_INACT_01",
            dev_name="Spare Sensor",
            dev_type="TS",
            hub_id="HUB_TEST_M3",
            is_active=False,
            room_id=room_id,
            marker_x=50.0,
            marker_y=50.0,
            created_at=datetime.now(UTC)
        )
        db.add_all([dev_ts, dev_ats, dev_inactive])

        # Add telemetry records
        ts_telemetry = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id="DEV_MAP_TS_01",
            timestamp=datetime.now(UTC),
            temp=23.8,
            humid=55.2
        )
        ats_telemetry = ats_data(
            data_id=str(uuid.uuid4()),
            dev_id="DEV_MAP_ATS_01",
            timestamp=datetime.now(UTC),
            state="PLN_ON",
            pln=220.5,
            genset=0.0,
            aki=13.8,
            rem_hour=0.0,
            rem_min=0.0,
            rem_sec=0.0,
            auto_mode=True,
            emergency=False
        )
        db.add_all([ts_telemetry, ats_telemetry])
        db.commit()
    finally:
        db.close()

    # 4. Test GET /api/rooms/{room_id}/map as Viewer
    map_resp = client.get(f"/api/rooms/{room_id}/map", cookies=viewer_cookies)
    assert map_resp.status_code == 200
    map_data = map_resp.json()

    assert map_data["room_id"] == room_id
    assert map_data["room_name"] == "Facility Control Room"
    assert map_data["has_image"] is True
    assert map_data["floor_plan_url"] == floor_plan_url
    assert len(map_data["devices"]) == 3

    # Verify device markers
    devices_by_id = {d["dev_id"]: d for d in map_data["devices"]}

    ts_marker = devices_by_id["DEV_MAP_TS_01"]
    assert ts_marker["dev_name"] == "Temperature Sensor A"
    assert ts_marker["dev_type"] == "TS"
    assert ts_marker["marker_x"] == 15.5
    assert ts_marker["marker_y"] == 30.0
    assert ts_marker["is_active"] is True
    assert ts_marker["status"] == "active"
    assert ts_marker["latest_reading"] is not None
    assert ts_marker["latest_reading"]["temp"] == 23.8
    assert ts_marker["latest_reading"]["humid"] == 55.2

    ats_marker = devices_by_id["DEV_MAP_ATS_01"]
    assert ats_marker["dev_name"] == "Main Generator ATS"
    assert ats_marker["dev_type"] == "ATS"
    assert ats_marker["marker_x"] == 80.0
    assert ats_marker["marker_y"] == 75.5
    assert ats_marker["is_active"] is True
    assert ats_marker["status"] == "active"
    assert ats_marker["latest_reading"]["state"] == "PLN_ON"
    assert ats_marker["latest_reading"]["pln"] == 220.5
    assert ats_marker["latest_reading"]["auto_mode"] is True

    inact_marker = devices_by_id["DEV_MAP_INACT_01"]
    assert inact_marker["is_active"] is False
    assert inact_marker["status"] == "inactive"

    # Also verify operator and admin access
    assert client.get(f"/api/rooms/{room_id}/map", cookies=operator_cookies).status_code == 200
    assert client.get(f"/api/rooms/{room_id}/map", cookies=admin_cookies).status_code == 200


def test_get_room_map_no_image_graceful():
    viewer_cookies = get_auth_cookies("viewer_m3", "viewerpass")
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    # 1. Create a room with no floor plan image
    create_resp = client.post(
        "/api/rooms",
        json={"name": "No Image Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 2. Query map endpoint
    resp = client.get(f"/api/rooms/{room_id}/map", cookies=viewer_cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == room_id
    assert data["room_name"] == "No Image Room"
    assert data["has_image"] is False
    assert data["floor_plan_url"] is None
    assert data["devices"] == []

    # 3. Test when room has a path set in DB but the file is missing from disk
    db = SessionLocal()
    try:
        room = db.get(rooms, room_id)
        room.floor_plan_image_path = "/static/uploads/floorplans/non_existent_file_999.png"
        db.commit()
    finally:
        db.close()

    resp_missing = client.get(f"/api/rooms/{room_id}/map", cookies=viewer_cookies)
    assert resp_missing.status_code == 200
    data_missing = resp_missing.json()
    assert data_missing["has_image"] is False
    assert data_missing["floor_plan_url"] is None


def test_get_room_map_errors():
    viewer_cookies = get_auth_cookies("viewer_m3", "viewerpass")

    # 1. Unauthenticated -> 401
    client.cookies.clear()
    resp_unauth = client.get("/api/rooms/any_room/map")
    assert resp_unauth.status_code == 401

    # 2. Non-existent room -> 404
    resp_404 = client.get("/api/rooms/non_existent_room_xyz/map", cookies=viewer_cookies)
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["detail"].lower()


def test_delete_room_cleans_up_floor_plan_file():
    admin_cookies = get_auth_cookies("admin_m3", "adminpass")

    # 1. Create room
    create_resp = client.post(
        "/api/rooms",
        json={"name": "Delete Cleanup Room"},
        cookies=admin_cookies
    )
    room_id = create_resp.json()["id"]

    # 2. Upload floor plan image
    files = {"file": ("cleanup_plan.png", io.BytesIO(DUMMY_PNG_BYTES), "image/png")}
    upload_resp = client.post(f"/api/rooms/{room_id}/floor-plan", files=files, cookies=admin_cookies)
    assert upload_resp.status_code == 200
    url = upload_resp.json()["floor_plan_url"]
    disk_path = resolve_static_disk_path(url)
    assert os.path.exists(disk_path)

    # 3. Delete room
    del_resp = client.delete(f"/api/rooms/{room_id}", cookies=admin_cookies)
    assert del_resp.status_code == 200

    # 4. Verify file was unlinked from disk
    assert not os.path.exists(disk_path), "Floor plan file was not removed upon room deletion!"
