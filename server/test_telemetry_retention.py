from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import app.services.telemetry_retention as retention
from app.routers.devices import _tiered_history
from modelsv5 import (
    Base, ats_data, ats_hourly, dev_table, hub_table, temperature_data,
    temperature_hourly,
)


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False)


def _seed_devices(db):
    db.add(hub_table(hub_id="hub", hub_name="Hub", hub_key="key"))
    db.add_all([
        dev_table(dev_id="ts", dev_name="TS", dev_type="TS", hub_id="hub"),
        dev_table(dev_id="ats", dev_name="ATS", dev_type="ATS", hub_id="hub"),
    ])
    db.commit()


def test_rollup_models_have_unique_composite_indexes():
    engine, _ = _session_factory()
    inspector = inspect(engine)
    for table in ("temperature_hourly", "temperature_daily", "temperature_monthly", "ats_hourly", "ats_daily", "ats_monthly"):
        assert {"dev_id", "bucket_start"}.issubset({column["name"] for column in inspector.get_columns(table)})
        assert any(index["unique"] and index["column_names"] == ["dev_id", "bucket_start"] for index in inspector.get_indexes(table))


def test_shift_months_preserves_calendar_day_and_clamps_month_end():
    assert retention._shift_months(datetime(2026, 9, 14, 12, tzinfo=UTC), -3) == datetime(2026, 6, 14, 12, tzinfo=UTC)
    assert retention._shift_months(datetime(2026, 3, 31, 12, tzinfo=UTC), -1) == datetime(2026, 2, 28, 12, tzinfo=UTC)


def test_raw_rollup_is_weighted_null_safe_idempotent_and_accepts_late_data(monkeypatch):
    _, factory = _session_factory()
    monkeypatch.setattr(retention, "SessionLocal", factory)
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    bucket = now - timedelta(days=40)
    bucket = bucket.replace(minute=0)
    db = factory()
    _seed_devices(db)
    db.add_all([
        temperature_data(data_id="t1", dev_id="ts", timestamp=bucket, temp=10, humid=None),
        temperature_data(data_id="t2", dev_id="ts", timestamp=bucket + timedelta(minutes=1), temp=20, humid=60),
        ats_data(data_id="a1", dev_id="ats", timestamp=bucket, state="PLN", pln=220, genset=0, aki=12, rem_hour=0, rem_min=0, rem_sec=0, auto_mode=True, emergency=False),
        ats_data(data_id="a2", dev_id="ats", timestamp=bucket + timedelta(minutes=1), state="GENSET", pln=0, genset=220, aki=11, rem_hour=0, rem_min=0, rem_sec=0, auto_mode=True, emergency=True),
    ])
    db.commit()

    retention.run_telemetry_retention(now)
    rollup = db.query(temperature_hourly).one()
    assert (rollup.temp_sum, rollup.temp_count, rollup.temp_avg) == (30, 2, 15)
    assert (rollup.humid_sum, rollup.humid_count, rollup.humid_avg) == (60, 1, 60)
    ats = db.query(ats_hourly).one()
    assert (ats.first_state, ats.last_state, ats.state_change_count, ats.emergency_event_count) == ("PLN", "GENSET", 1, 1)
    assert db.query(temperature_data).count() == 0

    assert retention.run_telemetry_retention(now)["temperature_hourly"] == 0
    db.add(temperature_data(data_id="late", dev_id="ts", timestamp=bucket + timedelta(minutes=2), temp=30, humid=None))
    db.commit()
    retention.run_telemetry_retention(now)
    db.refresh(rollup)
    assert (rollup.temp_sum, rollup.temp_count, rollup.temp_avg) == (60, 3, 20)
    assert (rollup.humid_sum, rollup.humid_count, rollup.humid_avg) == (60, 1, 60)


def test_raw_retention_only_moves_closed_hours_older_than_31_days(monkeypatch):
    _, factory = _session_factory()
    monkeypatch.setattr(retention, "SessionLocal", factory)
    now = datetime(2026, 9, 14, 12, 30, tzinfo=UTC)
    cutoff = (now - timedelta(days=31)).replace(minute=0, second=0, microsecond=0)
    db = factory()
    _seed_devices(db)
    db.add_all([
        temperature_data(data_id="old", dev_id="ts", timestamp=cutoff - timedelta(seconds=1), temp=1, humid=1),
        temperature_data(data_id="edge", dev_id="ts", timestamp=cutoff, temp=2, humid=2),
    ])
    db.commit()
    retention.run_telemetry_retention(now)
    assert {row.data_id for row in db.query(temperature_data).all()} == {"edge"}
    assert db.query(temperature_hourly).count() == 1


def test_tiered_history_combines_raw_and_rollup_with_weighted_average():
    _, factory = _session_factory()
    db = factory()
    _seed_devices(db)
    day = datetime(2026, 9, 1, tzinfo=UTC)
    db.add(temperature_hourly(
        dev_id="ts", bucket_start=day, temp_sum=20, temp_count=2, temp_avg=10,
        temp_min=5, temp_max=15, humid_sum=0, humid_count=0,
    ))
    db.add(temperature_data(data_id="late-api", dev_id="ts", timestamp=day + timedelta(hours=1), temp=40, humid=50))
    db.commit()
    points = _tiered_history(db, "ts", "temperature", day, day + timedelta(days=1), "day")
    assert len(points) == 1
    assert (points[0].temp, points[0].temp_min, points[0].temp_max) == (20, 5, 40)
    assert points[0].humid == 50
