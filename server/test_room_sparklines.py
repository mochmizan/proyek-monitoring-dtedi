# test_room_sparklines.py
# Unit and integration tests for GET /api/rooms/sparklines (Two-Pass Room Sparklines)

import os
import uuid
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.dialects import postgresql, sqlite

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    rooms, temperature_data, ats_data, data_table
)
from auth import hash_password
from app.main import api
from app.routers.devices import _build_epoch_bucket_expr

client = TestClient(api)
api.state.limiter.enabled = False


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        # Clear tables
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Seed test user
        user = User(
            id="user-viewer-spark",
            username="viewer_spark",
            password_hash=hash_password("sparkpass"),
            display_name="Viewer Spark",
            role="viewer",
        )
        db.add(user)

        # Seed test hub
        hub = hub_table(
            hub_id="HUB_SPARK_1",
            hub_name="Spark Hub 1",
            hub_key="secret_spark_1",
            is_active=True,
        )
        db.add(hub)

        # Seed 4 test rooms
        r_multi = rooms(id="room_multi", name="Multi Device Room", hub_id="HUB_SPARK_1")
        r_part = rooms(id="room_part_null", name="Partial Null Room", hub_id="HUB_SPARK_1")
        r_full = rooms(id="room_full_null", name="Full Null Room", hub_id="HUB_SPARK_1")
        r_empty = rooms(id="room_empty", name="Empty Room", hub_id="HUB_SPARK_1")
        db.add_all([r_multi, r_part, r_full, r_empty])

        # Seed devices
        d1 = dev_table(dev_id="dev_m1", dev_name="TS Sensor 1", dev_type="TS", room_id="room_multi", hub_id="HUB_SPARK_1", is_active=True)
        d2 = dev_table(dev_id="dev_m2", dev_name="AC Unit 2", dev_type="AC", room_id="room_multi", hub_id="HUB_SPARK_1", is_active=True)
        d3 = dev_table(dev_id="dev_p1", dev_name="TS Part 1", dev_type="TS", room_id="room_part_null", hub_id="HUB_SPARK_1", is_active=True)
        d4 = dev_table(dev_id="dev_p2", dev_name="TS Part 2", dev_type="TS", room_id="room_part_null", hub_id="HUB_SPARK_1", is_active=True)
        d5 = dev_table(dev_id="dev_f1", dev_name="TS Full 1", dev_type="TS", room_id="room_full_null", hub_id="HUB_SPARK_1", is_active=True)
        d6 = dev_table(dev_id="dev_f2", dev_name="TS Full 2", dev_type="TS", room_id="room_full_null", hub_id="HUB_SPARK_1", is_active=True)
        db.add_all([d1, d2, d3, d4, d5, d6])

        # Seed telemetry clustered in a recent 5-minute window
        now = datetime.now(UTC)
        t1 = now - timedelta(minutes=15)

        # Room Multi: dev_m1=25.0, dev_m2=29.0 -> room max = 29.0
        # humid: dev_m1=50.0, dev_m2=65.0 -> room max = 65.0
        rec_m1 = temperature_data(data_id="rec_m1", dev_id="dev_m1", timestamp=t1, temp=25.0, humid=50.0)
        rec_m2 = temperature_data(data_id="rec_m2", dev_id="dev_m2", timestamp=t1, temp=29.0, humid=65.0)

        # Room Partial Null: dev_p1=25.0, dev_p2=None -> room max = 25.0
        # humid: dev_p1=None, dev_p2=70.0 -> room max = 70.0
        rec_p1 = temperature_data(data_id="rec_p1", dev_id="dev_p1", timestamp=t1, temp=25.0, humid=None)
        rec_p2 = temperature_data(data_id="rec_p2", dev_id="dev_p2", timestamp=t1, temp=None, humid=70.0)

        # Room Full Null: dev_f1=None, dev_f2=None -> room max = None
        rec_f1 = temperature_data(data_id="rec_f1", dev_id="dev_f1", timestamp=t1, temp=None, humid=None)
        rec_f2 = temperature_data(data_id="rec_f2", dev_id="dev_f2", timestamp=t1, temp=None, humid=None)

        db.add_all([rec_m1, rec_m2, rec_p1, rec_p2, rec_f1, rec_f2])
        db.commit()
    finally:
        db.close()


def get_auth_cookies() -> dict:
    resp = client.post("/api/auth/login", json={"username": "viewer_spark", "password": "sparkpass"})
    assert resp.status_code == 200
    return {"session_id": resp.cookies["session_id"]}


def test_room_sparklines_multi_device_max():
    """Verify Pass 2 MAX aggregation across multiple devices in same room/bucket."""
    cookies = get_auth_cookies()
    resp = client.get("/api/rooms/sparklines?range=6h&max_points=24", cookies=cookies)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "room_multi" in data
    spark = data["room_multi"]
    assert len(spark["points"]) >= 1
    # Check that temp is max(25.0, 29.0) = 29.0 and humid is max(50.0, 65.0) = 65.0
    pt = spark["points"][0]
    assert pt["temp"] == 29.0
    assert pt["humid"] == 65.0


def test_room_sparklines_partial_null():
    """Verify ANSI SQL MAX ignores NULL when at least one device has valid telemetry."""
    cookies = get_auth_cookies()
    resp = client.get("/api/rooms/sparklines?range=6h&max_points=24", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert "room_part_null" in data
    spark = data["room_part_null"]
    assert len(spark["points"]) >= 1
    pt = spark["points"][0]
    assert pt["temp"] == 25.0
    assert pt["humid"] == 70.0


def test_room_sparklines_full_null():
    """Verify ANSI SQL MAX produces None/null when all devices have NULL telemetry."""
    cookies = get_auth_cookies()
    resp = client.get("/api/rooms/sparklines?range=6h&max_points=24", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert "room_full_null" in data
    spark = data["room_full_null"]
    assert len(spark["points"]) >= 1
    pt = spark["points"][0]
    assert pt["temp"] is None
    assert pt["humid"] is None


def test_room_sparklines_empty_room():
    """Verify empty rooms or rooms without telemetry return points: []."""
    cookies = get_auth_cookies()
    resp = client.get("/api/rooms/sparklines?range=6h&max_points=24", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert "room_empty" in data
    assert data["room_empty"]["points"] == []


def test_room_sparklines_room_ids_filter():
    """Verify filtering by room_ids returns exactly the queried rooms."""
    cookies = get_auth_cookies()
    resp = client.get("/api/rooms/sparklines?room_ids=room_multi&room_ids=room_empty", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()

    assert "room_multi" in data
    assert "room_empty" in data
    assert "room_part_null" not in data
    assert "room_full_null" not in data


def test_room_sparklines_range_and_points_validation():
    """Verify invalid range and out-of-bound max_points return proper validation errors."""
    cookies = get_auth_cookies()

    # Invalid range -> 400
    resp = client.get("/api/rooms/sparklines?range=100y", cookies=cookies)
    assert resp.status_code == 400
    assert "Invalid range" in resp.json()["detail"]

    # max_points < 5 -> 422
    resp = client.get("/api/rooms/sparklines?max_points=3", cookies=cookies)
    assert resp.status_code in (422, 400)


def test_two_pass_cte_dialect_compilation():
    """Verify CTE compiles cleanly to both SQLite and PostgreSQL dialects."""
    bucket_sec = 300

    # 1. SQLite dialect
    b_sqlite = _build_epoch_bucket_expr("sqlite", temperature_data.timestamp, bucket_sec)
    p1_sqlite = select(
        dev_table.room_id.label("room_id"),
        dev_table.dev_id.label("dev_id"),
        b_sqlite,
        func.avg(temperature_data.temp).label("dev_temp"),
        func.avg(temperature_data.humid).label("dev_humid"),
    ).join(dev_table, temperature_data.dev_id == dev_table.dev_id).group_by(
        dev_table.room_id, dev_table.dev_id, b_sqlite
    )
    cte_sqlite = p1_sqlite.cte("device_bucket_agg")
    p2_sqlite = select(
        cte_sqlite.c.room_id,
        cte_sqlite.c.bucket_ts,
        func.max(cte_sqlite.c.dev_temp).label("room_temp"),
        func.max(cte_sqlite.c.dev_humid).label("room_humid"),
    ).group_by(cte_sqlite.c.room_id, cte_sqlite.c.bucket_ts).order_by(cte_sqlite.c.room_id.asc(), cte_sqlite.c.bucket_ts.asc())

    sql_sqlite = str(p2_sqlite.compile(dialect=sqlite.dialect()))
    assert "unixepoch" in sql_sqlite
    assert "device_bucket_agg" in sql_sqlite

    # 2. PostgreSQL dialect
    b_pg = _build_epoch_bucket_expr("postgresql", temperature_data.timestamp, bucket_sec)
    p1_pg = select(
        dev_table.room_id.label("room_id"),
        dev_table.dev_id.label("dev_id"),
        b_pg,
        func.avg(temperature_data.temp).label("dev_temp"),
        func.avg(temperature_data.humid).label("dev_humid"),
    ).join(dev_table, temperature_data.dev_id == dev_table.dev_id).group_by(
        dev_table.room_id, dev_table.dev_id, b_pg
    )
    cte_pg = p1_pg.cte("device_bucket_agg")
    p2_pg = select(
        cte_pg.c.room_id,
        cte_pg.c.bucket_ts,
        func.max(cte_pg.c.dev_temp).label("room_temp"),
        func.max(cte_pg.c.dev_humid).label("room_humid"),
    ).group_by(cte_pg.c.room_id, cte_pg.c.bucket_ts).order_by(cte_pg.c.room_id.asc(), cte_pg.c.bucket_ts.asc())

    sql_pg = str(p2_pg.compile(dialect=postgresql.dialect()))
    assert "EXTRACT(epoch FROM" in sql_pg
    assert "device_bucket_agg" in sql_pg
