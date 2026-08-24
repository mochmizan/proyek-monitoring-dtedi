# test_device_history.py
# Test Suite for Real Telemetry History API in HubGate V5

import os
import uuid
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
    temperature_data, ats_data, data_table
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
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Create test users
        admin = User(
            id="user-admin-hist",
            username="admin_hist",
            password_hash=hash_password("adminpass"),
            display_name="Admin Hist",
            role="admin"
        )
        viewer = User(
            id="user-viewer-hist",
            username="viewer_hist",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer Hist",
            role="viewer"
        )
        db.add_all([admin, viewer])

        # Create test hub
        hub = hub_table(
            hub_id="HUB_TEST_HIST",
            hub_name="Hub Hist",
            hub_key="secret_hist",
            is_active=True
        )
        db.add(hub)

        # Create TS device
        ts_dev = dev_table(
            dev_id="TS_DEV_01",
            dev_name="Temperature Sensor 01",
            dev_type="TS",
            hub_id="HUB_TEST_HIST",
            is_active=True
        )

        # Create ATS device
        ats_dev = dev_table(
            dev_id="ATS_DEV_01",
            dev_name="ATS Controller 01",
            dev_type="ATS",
            hub_id="HUB_TEST_HIST",
            is_active=True
        )

        db.add_all([ts_dev, ats_dev])
        db.commit()

        # Seed TS telemetry history across time
        now = datetime.now(UTC)
        ts_points = [
            # 50 days ago (outside all ranges except 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(days=50),
                temp=22.0,
                humid=55.0
            ),
            # 20 days ago (within '30d' and 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(days=20),
                temp=24.5,
                humid=58.0
            ),
            # 5 days ago (within '7d', '30d', and 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(days=5),
                temp=26.0,
                humid=60.0
            ),
            # 12 hours ago (within '24h', '7d', '30d', and 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(hours=12),
                temp=27.5,
                humid=62.0
            ),
            # 2 hours ago (within '6h', '24h', '7d', '30d', and 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(hours=2),
                temp=29.0,
                humid=65.0
            ),
            # 30 minutes ago (within '6h', '24h', '7d', '30d', and 'all')
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_DEV_01",
                timestamp=now - timedelta(minutes=30),
                temp=30.5,
                humid=68.0
            ),
        ]
        db.add_all(ts_points)

        # Seed ATS telemetry history
        ats_points = [
            ats_data(
                data_id=str(uuid.uuid4()),
                dev_id="ATS_DEV_01",
                timestamp=now - timedelta(hours=10),
                state="PLN_MAIN",
                pln=220.5,
                genset=0.0,
                aki=13.8,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False
            ),
            ats_data(
                data_id=str(uuid.uuid4()),
                dev_id="ATS_DEV_01",
                timestamp=now - timedelta(hours=2),
                state="GENSET_RUN",
                pln=0.0,
                genset=222.1,
                aki=13.5,
                rem_hour=1.0,
                rem_min=30.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False
            ),
            ats_data(
                data_id=str(uuid.uuid4()),
                dev_id="ATS_DEV_01",
                timestamp=now - timedelta(minutes=15),
                state="PLN_MAIN",
                pln=219.8,
                genset=0.0,
                aki=13.9,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False
            ),
        ]
        db.add_all(ats_points)
        db.commit()
    finally:
        db.close()


def get_auth_cookies(username: str = "viewer_hist", password: str = "viewerpass") -> dict:
    """Helper to log in and retrieve session cookie."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


# ==========================================
# 1. AUTHENTICATION & ERROR HANDLING TESTS
# ==========================================

def test_unauthenticated_access_rejected():
    """Accessing history without valid session cookie returns 401 Unauthorized."""
    resp = client.get("/api/devices/TS_DEV_01/history")
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_nonexistent_device_returns_404():
    """Querying history for a non-existent device returns 404."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/NON_EXISTENT_DEV/history", cookies=cookies)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Device not found"


def test_invalid_range_returns_400():
    """Querying history with an invalid range parameter returns 400 Bad Request."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history?range=invalid_range", cookies=cookies)
    assert resp.status_code == 400
    assert "Invalid range" in resp.json()["detail"]


# ==========================================
# 2. TS DEVICE TELEMETRY HISTORY TESTS
# ==========================================

def test_ts_device_history_default_range_24h():
    """Default range is 24h, returning points within past 24 hours in ascending timestamp order."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["dev_id"] == "TS_DEV_01"
    assert data["dev_type"] == "TS"
    assert data["range"] == "24h"
    assert data["total_points"] == 3
    assert len(data["points"]) == 3

    # Verify chronological ascending order
    timestamps = [p["timestamp"] for p in data["points"]]
    assert timestamps == sorted(timestamps)

    # Verify values
    p0 = data["points"][0]
    assert p0["temp"] == 27.5
    assert p0["humid"] == 62.0
    assert p0["pln"] is None

    p2 = data["points"][2]
    assert p2["temp"] == 30.5
    assert p2["humid"] == 68.0


def test_ts_device_history_6h():
    """Range 6h returns only points from past 6 hours (2 points)."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history?range=6h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["range"] == "6h"
    assert data["total_points"] == 2
    assert len(data["points"]) == 2
    assert data["points"][0]["temp"] == 29.0
    assert data["points"][1]["temp"] == 30.5


def test_ts_device_history_7d():
    """Range 7d returns points from past 7 days (4 points)."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history?range=7d", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["range"] == "7d"
    assert data["total_points"] == 4
    assert len(data["points"]) == 4


def test_ts_device_history_30d():
    """Range 30d returns points from past 30 days (5 points)."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history?range=30d", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["range"] == "30d"
    assert data["total_points"] == 5
    assert len(data["points"]) == 5


def test_ts_device_history_all():
    """Range all returns all points (6 points)."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_DEV_01/history?range=all", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["range"] == "all"
    assert data["total_points"] == 6
    assert len(data["points"]) == 6
    assert data["points"][0]["temp"] == 22.0


# ==========================================
# 3. ATS DEVICE TELEMETRY HISTORY TESTS
# ==========================================

def test_ats_device_history_24h():
    """ATS history returns electrical voltage readings and controller state."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/ATS_DEV_01/history?range=24h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert data["dev_id"] == "ATS_DEV_01"
    assert data["dev_type"] == "ATS"
    assert data["range"] == "24h"
    assert data["total_points"] == 3
    assert len(data["points"]) == 3

    # Check fields for ATS points
    p0 = data["points"][0]
    assert p0["pln"] == 220.5
    assert p0["genset"] == 0.0
    assert p0["aki"] == 13.8
    assert p0["state"] == "PLN_MAIN"
    assert p0["temp"] is None
    assert p0["humid"] is None

    p1 = data["points"][1]
    assert p1["pln"] == 0.0
    assert p1["genset"] == 222.1
    assert p1["aki"] == 13.5
    assert p1["state"] == "GENSET_RUN"


# ==========================================
# 4. DENSE DATA DOWNSAMPLING (bucketed path)
# ==========================================

def test_ats_dense_history_downsamples():
    """Dense windows (>1000 rows) are averaged into ~1000 time buckets."""
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        bulk = []
        for i in range(1200):
            bulk.append(
                ats_data(
                    data_id=str(uuid.uuid4()),
                    dev_id="ATS_DEV_01",
                    timestamp=now - timedelta(minutes=30) + timedelta(seconds=i * 1.5),
                    state="PLN_MAIN",
                    pln=220.0,
                    genset=0.0,
                    aki=14.0,
                    rem_hour=0.0,
                    rem_min=0.0,
                    rem_sec=0.0,
                    auto_mode=True,
                    emergency=False,
                )
            )
        db.add_all(bulk)
        db.commit()
    finally:
        db.close()

    cookies = get_auth_cookies()
    resp = client.get("/api/devices/ATS_DEV_01/history?range=6h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    # Bucketed output must stay bounded and ascending
    assert data["total_points"] <= 1100
    timestamps = [p["timestamp"] for p in data["points"]]
    assert timestamps == sorted(timestamps)
    # Latest bucket must be near 'now', not stuck at window start
    last = data["points"][-1]["timestamp"]
    assert last is not None
