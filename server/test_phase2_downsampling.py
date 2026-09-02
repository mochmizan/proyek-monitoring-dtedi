# test_phase2_downsampling.py
# Comprehensive Test Suite for Phase 2 High-Performance Downsampling

import os
import time
import uuid
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    temperature_data, ats_data, data_table, rooms,
    pending_commands, schedules, device_threshold_config
)
from auth import hash_password
from hubgatev5 import api

client = TestClient(api)
api.state.limiter.enabled = False

# SQL statement interceptor to verify zero count(*) queries
executed_sql_queries: list[str] = []


def _sql_logger(conn, cursor, statement, parameters, context, executemany):
    executed_sql_queries.append(statement)


# Register listener once
event.listen(engine, "before_cursor_execute", _sql_logger)


def reset_sql_tracker():
    executed_sql_queries.clear()


def get_auth_cookies(username: str = "viewer_p2", password: str = "viewerpass") -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


@pytest.fixture(scope="module", autouse=True)
def setup_downsampling_environment():
    db = SessionLocal()
    try:
        # Create test users
        user = db.query(User).filter(User.username == "viewer_p2").first()
        if not user:
            user = User(
                id="user-viewer-p2",
                username="viewer_p2",
                password_hash=hash_password("viewerpass"),
                display_name="Viewer Phase 2",
                role="viewer",
            )
            db.add(user)

        # Create test hub
        hub = db.query(hub_table).filter(hub_table.hub_id == "HUB_P2").first()
        if not hub:
            hub = hub_table(
                hub_id="HUB_P2",
                hub_name="Hub Phase 2",
                hub_key="secret_p2",
                is_active=True,
            )
            db.add(hub)

        # Create TS device
        ts_dev = db.query(dev_table).filter(dev_table.dev_id == "TS_P2_DEV").first()
        if not ts_dev:
            ts_dev = dev_table(
                dev_id="TS_P2_DEV",
                dev_name="Temp Sensor P2",
                dev_type="TS",
                hub_id="HUB_P2",
                is_active=True,
            )
            db.add(ts_dev)

        # Create ATS device
        ats_dev = db.query(dev_table).filter(dev_table.dev_id == "ATS_P2_DEV").first()
        if not ats_dev:
            ats_dev = dev_table(
                dev_id="ATS_P2_DEV",
                dev_name="ATS Sensor P2",
                dev_type="ATS",
                hub_id="HUB_P2",
                is_active=True,
            )
            db.add(ats_dev)

        # Create Empty device
        empty_dev = db.query(dev_table).filter(dev_table.dev_id == "EMPTY_P2_DEV").first()
        if not empty_dev:
            empty_dev = dev_table(
                dev_id="EMPTY_P2_DEV",
                dev_name="Empty Sensor P2",
                dev_type="TS",
                hub_id="HUB_P2",
                is_active=True,
            )
            db.add(empty_dev)

        # Clean existing telemetry records for these devices
        db.query(temperature_data).filter(temperature_data.dev_id.in_(["TS_P2_DEV", "EMPTY_P2_DEV"])).delete()
        db.query(ats_data).filter(ats_data.dev_id == "ATS_P2_DEV").delete()
        db.commit()

        # Seed baseline TS telemetry
        now = datetime.now(UTC)
        # Point 1: 5 days ago
        # Point 2: 10 hours ago
        # Point 3: 3 hours ago
        # Point 4: 15 minutes ago
        db.add_all([
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_P2_DEV",
                timestamp=now - timedelta(days=5),
                temp=21.0,
                humid=50.0,
            ),
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_P2_DEV",
                timestamp=now - timedelta(hours=10),
                temp=25.0,
                humid=55.0,
            ),
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_P2_DEV",
                timestamp=now - timedelta(hours=3),
                temp=28.0,
                humid=60.0,
            ),
            temperature_data(
                data_id=str(uuid.uuid4()),
                dev_id="TS_P2_DEV",
                timestamp=now - timedelta(minutes=15),
                temp=31.0,
                humid=65.0,
            ),
        ])

        # Seed baseline ATS telemetry
        db.add_all([
            ats_data(
                data_id=str(uuid.uuid4()),
                dev_id="ATS_P2_DEV",
                timestamp=now - timedelta(hours=8),
                state="PLN_MAIN",
                pln=220.0,
                genset=0.0,
                aki=13.8,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False,
            ),
            ats_data(
                data_id=str(uuid.uuid4()),
                dev_id="ATS_P2_DEV",
                timestamp=now - timedelta(hours=2),
                state="GENSET_RUN",
                pln=0.0,
                genset=221.5,
                aki=13.6,
                rem_hour=1.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False,
            ),
        ])
        db.commit()
    finally:
        db.close()


# ==========================================
# 1. ZERO COUNT(*) INVARIANT VERIFICATION
# ==========================================

def test_zero_count_queries_on_all_standard_ranges():
    """Verify zero SELECT count(*) statements are executed across all ranges."""
    cookies = get_auth_cookies()

    for r in ["6h", "24h", "7d", "30d", "all"]:
        reset_sql_tracker()
        resp = client.get(f"/api/devices/TS_P2_DEV/history?range={r}", cookies=cookies)
        assert resp.status_code == 200, f"Failed for range {r}"
        
        # Invariant: No query contains count(
        count_queries = [q for q in executed_sql_queries if "count(" in q.lower()]
        assert len(count_queries) == 0, f"Found count(*) query for range {r}: {count_queries}"


def test_zero_count_queries_on_ats_and_custom():
    """Verify zero SELECT count(*) on ATS device and custom window query."""
    cookies = get_auth_cookies()
    now = datetime.now(UTC)
    start_str = (now - timedelta(hours=12)).isoformat()
    end_str = now.isoformat()

    reset_sql_tracker()
    resp = client.get(
        f"/api/devices/ATS_P2_DEV/history?start_time={start_str}&end_time={end_str}&max_points=500",
        cookies=cookies,
    )
    assert resp.status_code == 200
    count_queries = [q for q in executed_sql_queries if "count(" in q.lower()]
    assert len(count_queries) == 0, f"Found count(*) query on custom ATS query: {count_queries}"


# ==========================================
# 2. ACCURATE AVG, MIN, MAX ENVELOPE TESTS
# ==========================================

def test_ts_envelope_accuracy_known_fixture():
    """Verify avg, min, max are accurately calculated for TS data in the same bucket."""
    db = SessionLocal()
    dev_id = "TS_ENVELOPE_DEV"
    try:
        # Create temporary device
        dev = dev_table(
            dev_id=dev_id,
            dev_name="Envelope TS Dev",
            dev_type="TS",
            hub_id="HUB_P2",
            is_active=True,
        )
        db.merge(dev)
        db.query(temperature_data).filter(temperature_data.dev_id == dev_id).delete()
        db.commit()

        # Seed 3 points tightly clustered in time (safely inside a single 216s bucket)
        now_epoch = int(datetime.now(UTC).timestamp())
        base_epoch = ((now_epoch - 1200) // 216) * 216 + 10
        base_time = datetime.fromtimestamp(base_epoch, tz=UTC)
        p1 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time,
            temp=20.0,
            humid=40.0,
        )
        p2 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time + timedelta(seconds=2),
            temp=30.0,
            humid=50.0,
        )
        p3 = temperature_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time + timedelta(seconds=4),
            temp=40.0,
            humid=60.0,
        )
        db.add_all([p1, p2, p3])
        db.commit()

        cookies = get_auth_cookies()
        resp = client.get(
            f"/api/devices/{dev_id}/history?range=6h&max_points=100",
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_points"] == 1
        point = data["points"][0]

        # Avg = (20 + 30 + 40) / 3 = 30.0
        assert point["temp"] == 30.0
        assert point["temp_min"] == 20.0
        assert point["temp_max"] == 40.0

        # Humid Avg = (40 + 50 + 60) / 3 = 50.0
        assert point["humid"] == 50.0
        assert point["humid_min"] == 40.0
        assert point["humid_max"] == 60.0
    finally:
        db.query(temperature_data).filter(temperature_data.dev_id == dev_id).delete()
        db.query(dev_table).filter(dev_table.dev_id == dev_id).delete()
        db.commit()
        db.close()


def test_ats_envelope_and_state_accuracy_known_fixture():
    """Verify avg, min, max and state aggregation for ATS data."""
    db = SessionLocal()
    dev_id = "ATS_ENVELOPE_DEV"
    try:
        dev = dev_table(
            dev_id=dev_id,
            dev_name="Envelope ATS Dev",
            dev_type="ATS",
            hub_id="HUB_P2",
            is_active=True,
        )
        db.merge(dev)
        db.query(ats_data).filter(ats_data.dev_id == dev_id).delete()
        db.commit()

        # Seed 3 points within 4 seconds (safely inside a single 216s bucket)
        now_epoch = int(datetime.now(UTC).timestamp())
        base_epoch = ((now_epoch - 600) // 216) * 216 + 10
        base_time = datetime.fromtimestamp(base_epoch, tz=UTC)
        p1 = ats_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time,
            state="PLN_MAIN",
            pln=210.0,
            genset=0.0,
            aki=12.5,
            rem_hour=0.0, rem_min=0.0, rem_sec=0.0, auto_mode=True, emergency=False,
        )
        p2 = ats_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time + timedelta(seconds=2),
            state="GENSET_RUN",
            pln=220.0,
            genset=110.0,
            aki=13.0,
            rem_hour=0.0, rem_min=0.0, rem_sec=0.0, auto_mode=True, emergency=False,
        )
        p3 = ats_data(
            data_id=str(uuid.uuid4()),
            dev_id=dev_id,
            timestamp=base_time + timedelta(seconds=4),
            state="PLN_MAIN",
            pln=230.0,
            genset=220.0,
            aki=13.5,
            rem_hour=0.0, rem_min=0.0, rem_sec=0.0, auto_mode=True, emergency=False,
        )
        db.add_all([p1, p2, p3])
        db.commit()

        cookies = get_auth_cookies()
        resp = client.get(
            f"/api/devices/{dev_id}/history?range=6h&max_points=100",
            cookies=cookies,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_points"] == 1
        point = data["points"][0]

        # PLN: 210, 220, 230 -> avg 220.0, min 210.0, max 230.0
        assert point["pln"] == 220.0
        assert point["pln_min"] == 210.0
        assert point["pln_max"] == 230.0

        # Genset: 0, 110, 220 -> avg 110.0, min 0.0, max 220.0
        assert point["genset"] == 110.0
        assert point["genset_min"] == 0.0
        assert point["genset_max"] == 220.0

        # Aki: 12.5, 13.0, 13.5 -> avg 13.0, min 12.5, max 13.5
        assert point["aki"] == 13.0
        assert point["aki_min"] == 12.5
        assert point["aki_max"] == 13.5

        # State: max("GENSET_RUN", "PLN_MAIN") == "PLN_MAIN"
        assert point["state"] == "PLN_MAIN"
    finally:
        db.query(ats_data).filter(ats_data.dev_id == dev_id).delete()
        db.query(dev_table).filter(dev_table.dev_id == dev_id).delete()
        db.commit()
        db.close()


# ==========================================
# 3. SPARSE & DENSE TELEMETRY PERFORMANCE
# ==========================================

def test_sparse_telemetry_handling():
    """Sparse dataset (<1000 rows) returns accurately without unnecessary rows."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_P2_DEV/history?range=24h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    # In our setup, 3 points were in past 24h (10h, 3h, 15m ago)
    assert data["total_points"] == 3
    assert data["bucket_seconds"] is not None
    assert data["bucket_seconds"] > 0
    # Values should match individual records since they fall in different buckets
    timestamps = [p["timestamp"] for p in data["points"]]
    assert timestamps == sorted(timestamps)


def test_dense_telemetry_over_10000_rows():
    """Dense dataset (>10,000 rows) downsamples smoothly and rapidly without count(*)."""
    db = SessionLocal()
    dense_dev_id = "TS_DENSE_10K"
    try:
        dev = dev_table(
            dev_id=dense_dev_id,
            dev_name="Dense 10K Device",
            dev_type="TS",
            hub_id="HUB_P2",
            is_active=True,
        )
        db.merge(dev)
        db.query(temperature_data).filter(temperature_data.dev_id == dense_dev_id).delete()
        db.commit()

        # Seed 10,500 telemetry rows over a 24-hour window (~8.2 seconds interval)
        now = datetime.now(UTC)
        start_time = now - timedelta(hours=24)
        total_rows = 10500
        step_seconds = (24 * 3600) / total_rows

        records = []
        for i in range(total_rows):
            records.append(
                temperature_data(
                    data_id=str(uuid.uuid4()),
                    dev_id=dense_dev_id,
                    timestamp=start_time + timedelta(seconds=i * step_seconds),
                    temp=20.0 + (i % 50) * 0.2,
                    humid=50.0 + (i % 30) * 0.5,
                )
            )
        db.bulk_save_objects(records)
        db.commit()

        # Execute downsampled query with max_points=1000
        cookies = get_auth_cookies()
        reset_sql_tracker()

        t_start = time.perf_counter()
        resp = client.get(
            f"/api/devices/{dense_dev_id}/history?range=24h&max_points=1000",
            cookies=cookies,
        )
        t_elapsed = time.perf_counter() - t_start

        assert resp.status_code == 200
        data = resp.json()

        # 1. Output must be bounded to ~max_points (within 10% tolerance due to integer bucket epoch alignment)
        assert data["total_points"] <= 1100
        assert data["total_points"] >= 900
        assert len(data["points"]) == data["total_points"]

        # 2. Points must be sorted chronologically ascending
        timestamps = [p["timestamp"] for p in data["points"]]
        assert timestamps == sorted(timestamps)

        # 3. Min/Max envelopes are populated
        first_point = data["points"][0]
        assert first_point["temp"] is not None
        assert first_point["temp_min"] is not None
        assert first_point["temp_max"] is not None
        assert first_point["temp_min"] <= first_point["temp"] <= first_point["temp_max"]

        # 4. Zero count(*) statements were issued
        count_queries = [q for q in executed_sql_queries if "count(" in q.lower()]
        assert len(count_queries) == 0

        # 5. Execution was fast (sub-second on SQLite even for 10k rows)
        assert t_elapsed < 2.0, f"Query took too long: {t_elapsed:.3f}s"
    finally:
        db.query(temperature_data).filter(temperature_data.dev_id == dense_dev_id).delete()
        db.query(dev_table).filter(dev_table.dev_id == dense_dev_id).delete()
        db.commit()
        db.close()


# ==========================================
# 4. CUSTOM TIME RANGES & MAX_POINTS VALIDATION
# ==========================================

def test_custom_time_range_success():
    """Querying with ISO bounds start_time and end_time returns 'custom' range."""
    cookies = get_auth_cookies()
    now = datetime.now(UTC)
    start_dt = now - timedelta(hours=5)
    end_dt = now - timedelta(hours=1)

    resp = client.get(
        f"/api/devices/TS_P2_DEV/history?start_time={start_dt.isoformat()}&end_time={end_dt.isoformat()}&max_points=50",
        cookies=cookies,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["range"] == "custom"
    assert data["total_points"] <= 50
    # In setup, Point 3 is 3h ago (which falls within [5h ago, 1h ago])
    assert data["total_points"] == 1
    assert data["points"][0]["temp"] == 28.0


def test_custom_time_range_invalid_bounds():
    """start_time > end_time returns 400 Bad Request."""
    cookies = get_auth_cookies()
    now = datetime.now(UTC)
    start_dt = now
    end_dt = now - timedelta(hours=2)

    resp = client.get(
        f"/api/devices/TS_P2_DEV/history?start_time={start_dt.isoformat()}&end_time={end_dt.isoformat()}",
        cookies=cookies,
    )
    assert resp.status_code == 400
    assert "start_time must be earlier than or equal to end_time" in resp.json()["detail"]


def test_custom_time_range_invalid_format():
    """Malformed start_time returns 400 Bad Request."""
    cookies = get_auth_cookies()
    resp = client.get(
        "/api/devices/TS_P2_DEV/history?start_time=not-a-valid-datetime",
        cookies=cookies,
    )
    assert resp.status_code == 400
    assert "Invalid datetime format" in resp.json()["detail"]


def test_max_points_bounds_enforcement():
    """max_points is validated to be between 10 and 5000."""
    cookies = get_auth_cookies()

    # Below lower bound (ge=10)
    resp_low = client.get("/api/devices/TS_P2_DEV/history?max_points=5", cookies=cookies)
    assert resp_low.status_code == 422

    # Above upper bound (le=5000)
    resp_high = client.get("/api/devices/TS_P2_DEV/history?max_points=5001", cookies=cookies)
    assert resp_high.status_code == 422

    # Valid boundary points
    resp_min = client.get("/api/devices/TS_P2_DEV/history?max_points=10", cookies=cookies)
    assert resp_min.status_code == 200
    assert resp_min.json()["total_points"] <= 10

    resp_max = client.get("/api/devices/TS_P2_DEV/history?max_points=5000", cookies=cookies)
    assert resp_max.status_code == 200


# ==========================================
# 5. BACKWARD COMPATIBILITY & EDGE CASES
# ==========================================

def test_response_json_backward_compatibility():
    """Verify response structure conforms 100% to frontend and client expectations."""
    cookies = get_auth_cookies()
    resp = client.get("/api/devices/TS_P2_DEV/history?range=24h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    # Top-level keys
    assert "dev_id" in data
    assert "dev_type" in data
    assert "range" in data
    assert "total_points" in data
    assert "points" in data
    assert "bucket_seconds" in data
    assert isinstance(data["bucket_seconds"], int)

    # Point fields
    point = data["points"][0]
    expected_keys = {
        "timestamp", "temp", "humid", "pln", "genset", "aki", "state",
        "temp_min", "temp_max", "humid_min", "humid_max",
        "pln_min", "pln_max", "genset_min", "genset_max", "aki_min", "aki_max"
    }
    assert expected_keys.issubset(set(point.keys()))


def test_empty_device_history_returns_200():
    """Device with no telemetry records returns total_points=0, points=[] without error."""
    cookies = get_auth_cookies()

    # Range 24h
    resp = client.get("/api/devices/EMPTY_P2_DEV/history?range=24h", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_points"] == 0
    assert data["points"] == []

    # Range all
    resp_all = client.get("/api/devices/EMPTY_P2_DEV/history?range=all", cookies=cookies)
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["total_points"] == 0
    assert data_all["points"] == []
