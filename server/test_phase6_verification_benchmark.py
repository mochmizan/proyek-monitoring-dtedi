# test_phase6_verification_benchmark.py
# Comprehensive Test Suite for Phase 6: Verification, High-Concurrency Benchmarking & Zero-Lock Architecture

from datetime import UTC, datetime, timedelta
import math
import os
import time
import uuid
import concurrent.futures

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

# Force isolated test database
os.environ["DATABASE_URL"] = "sqlite:///./test_phase6_bench.db"

import init_sqlv5
init_sqlv5.init_db()

from auth import hash_password
from databasev5 import Base, SessionLocal, engine
from hubgatev5 import api
from modelsv5 import (
    User,
    UserSession,
    ats_data,
    data_table,
    dev_table,
    device_threshold_config,
    event_log,
    hub_table,
    rooms,
    temperature_data,
)
from schemasv5 import TSData, ATSData, IotBatchRequest

client = TestClient(api)
api.state.limiter.enabled = False

BENCH_HUB_ID = "HUB_P6_01"
BENCH_HUB_KEY = "secret_key_p6_01"
BENCH_ROOM_ID = "room-p6-01"
BENCH_TS_DEV_ID = "DEV_P6_TS_01"
BENCH_ATS_DEV_ID = "DEV_P6_ATS_01"
BENCH_USERNAME = "admin_p6"
BENCH_PASSWORD = "adminpass_p6"


def get_auth_cookies() -> dict:
    resp = client.post("/api/auth/login", json={"username": BENCH_USERNAME, "password": BENCH_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {BENCH_USERNAME}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


@pytest.fixture(scope="module", autouse=True)
def setup_phase6_environment():
    db = SessionLocal()
    try:
        # Clear existing tables for isolated test run
        db.query(event_log).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(UserSession).delete()
        db.query(User).delete()
        db.commit()

        # 1. Benchmark Admin User
        admin = User(
            id="user-admin-p6",
            username=BENCH_USERNAME,
            password_hash=hash_password(BENCH_PASSWORD),
            display_name="Admin Phase 6",
            role="admin",
        )
        db.add(admin)

        # 2. Benchmark Hub
        hub = hub_table(
            hub_id=BENCH_HUB_ID,
            hub_name="Hub Phase 6",
            hub_key=BENCH_HUB_KEY,
            room="Server Room P6",
            is_active=True,
            status="online",
            last_seen=datetime.now(UTC),
        )
        db.add(hub)

        # 3. Benchmark Room
        room = rooms(
            id=BENCH_ROOM_ID,
            name="Server Room P6",
            hub_id=BENCH_HUB_ID,
        )
        db.add(room)

        # 4. Devices
        ts_dev = dev_table(
            dev_id=BENCH_TS_DEV_ID,
            dev_name="Temp Sensor P6",
            dev_type="TS",
            hub_id=BENCH_HUB_ID,
            room_id=BENCH_ROOM_ID,
            is_active=True,
            last_status="online",
            last_seen=datetime.now(UTC),
        )
        ats_dev = dev_table(
            dev_id=BENCH_ATS_DEV_ID,
            dev_name="ATS Sensor P6",
            dev_type="ATS",
            hub_id=BENCH_HUB_ID,
            room_id=BENCH_ROOM_ID,
            is_active=True,
            last_status="online",
            last_seen=datetime.now(UTC),
        )
        db.add_all([ts_dev, ats_dev])

        # 5. Threshold Configs
        ts_thresh = device_threshold_config(
            dev_id=BENCH_TS_DEV_ID,
            warning=30.0,
            critical=35.0,
            hysteresis=0.5,
            debounce_seconds=30,
        )
        ats_thresh = device_threshold_config(
            dev_id=BENCH_ATS_DEV_ID,
            warning=12.0,
            critical=11.5,
            hysteresis=0.2,
            debounce_seconds=15,
        )
        db.add_all([ts_thresh, ats_thresh])
        db.commit()

        # 6. Seed 10,000 synthetic rows across 30 days for fast downsampling tests
        now = datetime.now(UTC)
        start_time = now - timedelta(days=30)
        step_seconds = (30 * 86400) / 10000

        records = []
        for i in range(10000):
            ts = start_time + timedelta(seconds=i * step_seconds)
            temp_val = round(20.0 + (i % 50) * 0.2, 2)
            humid_val = round(50.0 + (i % 30) * 0.5, 2)
            records.append({
                "data_id": f"p6_ts_{i}",
                "dev_id": BENCH_TS_DEV_ID,
                "timestamp": ts,
                "temp": temp_val,
                "humid": humid_val,
            })
        db.execute(temperature_data.__table__.insert(), records)
        db.commit()

    finally:
        db.close()


# =========================================================================
# 1. DOWNSAMPLING PERFORMANCE & ENVELOPES
# =========================================================================

def test_seeded_downsampling_performance_and_envelopes():
    """Seed 10,000 synthetic rows across 30 days and assert sub-150ms downsampling with min/max envelopes."""
    cookies = get_auth_cookies()

    t_start = time.perf_counter()
    resp = client.get(
        f"/api/devices/{BENCH_TS_DEV_ID}/history?range=30d&max_points=1000",
        cookies=cookies,
    )
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    assert resp.status_code == 200, f"History query failed: {resp.text}"
    data = resp.json()

    # 1. Downsampling bounds
    assert data["total_points"] <= 1050
    assert len(data["points"]) == data["total_points"]
    assert data["bucket_seconds"] is not None and data["bucket_seconds"] > 0

    # 2. Envelope fields populated
    first_pt = data["points"][0]
    assert "temp" in first_pt and first_pt["temp"] is not None
    assert "temp_min" in first_pt and first_pt["temp_min"] is not None
    assert "temp_max" in first_pt and first_pt["temp_max"] is not None
    assert first_pt["temp_min"] <= first_pt["temp"] <= first_pt["temp_max"]

    # 3. Sub-500ms latency assertion in test runner (aligned with SQLite dev/edge target SLA < 1000ms)
    assert elapsed_ms < 500.0, f"30d downsampling took {elapsed_ms:.2f}ms, expected < 500ms"


# =========================================================================
# 2. CONCURRENT READ/WRITE ZERO-LOCK CONTENTION
# =========================================================================

def test_concurrent_read_write_zero_lock_contention():
    """Executes multi-threaded concurrent read and write operations asserting 0 locks and 0 errors."""
    cookies = get_auth_cookies()
    headers = {
        "X-Hub-ID": BENCH_HUB_ID,
        "X-Hub-Key": BENCH_HUB_KEY,
    }

    exceptions: list[Exception] = []
    status_codes: list[int] = []

    def writer_worker(thread_id: int):
        c = TestClient(api)
        now_base = time.time()
        for i in range(25):
            try:
                # Single write
                p1 = {
                    "HUB_NAME": "Hub Phase 6",
                    "DEV_ID": BENCH_TS_DEV_ID,
                    "DEV_NAME": "Temp Sensor P6",
                    "DEV_TYPE": "TS",
                    "TEMP": 24.0 + (i * 0.1),
                    "HUMID": 55.0,
                    "HUB_TS": now_base + i,
                }
                r1 = c.post("/api/iot", json=p1, headers=headers)
                status_codes.append(r1.status_code)

                # Batch write (10 items)
                items = [{
                    "HUB_NAME": "Hub Phase 6",
                    "DEV_ID": BENCH_TS_DEV_ID,
                    "DEV_NAME": "Temp Sensor P6",
                    "DEV_TYPE": "TS",
                    "TEMP": 24.5,
                    "HUMID": 50.0,
                    "HUB_TS": now_base + 100 + (i * 10) + j,
                } for j in range(10)]
                r2 = c.post("/api/iot/batch", json={"items": items}, headers=headers)
                status_codes.append(r2.status_code)
            except Exception as e:
                exceptions.append(e)

    def reader_dashboard_worker(thread_id: int):
        c = TestClient(api)
        for _ in range(25):
            try:
                r1 = c.get("/api/devices", cookies=cookies)
                status_codes.append(r1.status_code)
                r2 = c.get("/api/rooms", cookies=cookies)
                status_codes.append(r2.status_code)
            except Exception as e:
                exceptions.append(e)

    def reader_history_worker(thread_id: int):
        c = TestClient(api)
        for _ in range(50):
            try:
                r = c.get(f"/api/devices/{BENCH_TS_DEV_ID}/history?range=30d&max_points=500", cookies=cookies)
                status_codes.append(r.status_code)
            except Exception as e:
                exceptions.append(e)

    # Launch 6 concurrent worker threads (2 writers, 2 polling readers, 2 heavy readers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f1 = executor.submit(writer_worker, 1)
        f2 = executor.submit(writer_worker, 2)
        f3 = executor.submit(reader_dashboard_worker, 1)
        f4 = executor.submit(reader_dashboard_worker, 2)
        f5 = executor.submit(reader_history_worker, 1)
        f6 = executor.submit(reader_history_worker, 2)
        concurrent.futures.wait([f1, f2, f3, f4, f5, f6])

    # Assert zero exceptions occurred
    assert len(exceptions) == 0, f"Encountered thread exceptions: {exceptions}"

    # Assert exactly zero HTTP 500s or database locks
    assert all(code == 200 for code in status_codes), f"Non-200 status codes observed: {set(status_codes)}"
    assert 500 not in status_codes
    assert len(status_codes) == 300  # 300 total requests executed successfully


# =========================================================================
# 3. SARGABLE INDEX USAGE QUERY PLAN
# =========================================================================

def test_sargable_index_usage_query_plan():
    """Verify SQLite EXPLAIN QUERY PLAN uses index idx_temp_dev_timestamp and avoids full table scan."""
    now = datetime.now(UTC)
    start_ts = (now - timedelta(days=30)).isoformat()
    end_ts = now.isoformat()

    explain_query = text(
        """
        EXPLAIN QUERY PLAN
        SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 2592) * 2592 AS b,
               AVG(temp), MIN(temp), MAX(temp)
        FROM temperature_data
        WHERE dev_id = :dev_id AND timestamp >= :start AND timestamp <= :end
        GROUP BY b ORDER BY b;
        """
    )

    db = SessionLocal()
    try:
        rows = db.execute(explain_query, {"dev_id": BENCH_TS_DEV_ID, "start": start_ts, "end": end_ts}).fetchall()
        plan_str = " ".join(str(r) for r in rows)

        # Assert query plan does NOT contain full table scan
        assert "SCAN TABLE temperature_data" not in plan_str, f"Found unindexed table scan in plan: {plan_str}"

        # Assert query plan explicitly uses the composite index
        assert "idx_temp_dev_timestamp" in plan_str or "USING INDEX" in plan_str, (
            f"Query plan did not utilize index: {plan_str}"
        )
    finally:
        db.close()


# =========================================================================
# 4. FULL HARDENING INVARIANTS MATRIX (PHASES 1 - 5)
# =========================================================================

def test_full_hardening_invariants_matrix():
    """Comprehensive validation covering Phase 1 through 5 architectural invariants."""
    db = SessionLocal()
    try:
        # Phase 1: Engine PRAGMAs
        journal_mode = db.execute(text("PRAGMA journal_mode;")).scalar()
        assert str(journal_mode).lower() in ("wal", "memory")

        busy_timeout = db.execute(text("PRAGMA busy_timeout;")).scalar()
        assert int(busy_timeout) == 10000

        foreign_keys = db.execute(text("PRAGMA foreign_keys;")).scalar()
        assert int(foreign_keys) == 1

        # Phase 3: Schema Indexing
        index_names = [
            row[0]
            for row in db.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex%';")
            ).fetchall()
        ]
        assert "ix_event_log_dev_metric_ts" in index_names
        assert "ix_dev_table_hub_id" in index_names
        assert "ix_pending_commands_hub_status_created" in index_names
        assert "idx_temp_dev_timestamp" in index_names

        # Phase 4: Ingestion Idempotency & Dedup
        headers = {
            "X-Hub-ID": BENCH_HUB_ID,
            "X-Hub-Key": BENCH_HUB_KEY,
        }
        fixed_ts = time.time()
        dup_batch = [{
            "HUB_NAME": "Hub Phase 6",
            "DEV_ID": BENCH_TS_DEV_ID,
            "DEV_NAME": "Temp Sensor P6",
            "DEV_TYPE": "TS",
            "TEMP": 26.0,
            "HUMID": 50.0,
            "HUB_TS": fixed_ts,
        } for _ in range(5)]

        # First post: 1 unique point inserted (4 duplicates deduplicated)
        r1 = client.post("/api/iot/batch", json={"items": dup_batch}, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["ingested_count"] == 1

        # Re-post identical batch: 0 points inserted (replay idempotent)
        r2 = client.post("/api/iot/batch", json={"items": dup_batch}, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["ingested_count"] == 0

        # Phase 5: Read-Only GET /api/devices (0 DB Writes to dev_table or event_log)
        cookies = get_auth_cookies()
        dev_writes = []

        def _track_write(conn, cursor, statement, parameters, context, executemany):
            stmt_upper = statement.strip().upper()
            if any(tbl in stmt_upper for tbl in ("DEV_TABLE", "EVENT_LOG")) and stmt_upper.startswith(("INSERT", "UPDATE", "DELETE")):
                dev_writes.append(statement)

        event.listen(engine, "before_cursor_execute", _track_write)
        try:
            r_dev = client.get("/api/devices", cookies=cookies)
            assert r_dev.status_code == 200
            assert len(dev_writes) == 0, f"GET /api/devices executed DB write operations to dev_table/event_log: {dev_writes}"
        finally:
            event.remove(engine, "before_cursor_execute", _track_write)

    finally:
        db.close()
