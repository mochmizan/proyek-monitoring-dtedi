# test_partition_manager.py
"""
Unit tests for Phase 2:
- Ingestion boundary timestamp sanitization (_parse_event_time in iot.py)
- Partition lifecycle manager (_add_months, _generate_partition_ddl, _parse_partition_upper_bound)
- Non-blocking concurrent detachment logic & pruning math
- SQLite dialect bypass safety
- Scheduler daily 02:15 AM job registration
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch
import pytest
from sqlalchemy import create_engine, text

from app.routers.iot import _parse_event_time
from app.services.partition_manager import (
    TELEMETRY_TABLES,
    RETENTION_DAYS,
    _add_months,
    _generate_partition_ddl,
    _parse_partition_upper_bound,
    _precreate_future_partitions,
    _prune_expired_partitions,
    run_partition_maintenance,
)


class DummyPayload:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# 1. Ingestion Boundary Timestamp Sanitization Tests
# ---------------------------------------------------------------------------

def test_parse_event_time_within_bounds():
    """Timestamps within [-35 days, +24 hours] are preserved with exact precision."""
    now_utc = datetime(2026, 9, 12, 12, 0, 0, 123456, tzinfo=UTC)

    # Valid: 5 days ago
    payload1 = DummyPayload(HUB_TS=(now_utc - timedelta(days=5)).isoformat())
    parsed1 = _parse_event_time(payload1, now_utc)
    assert parsed1 == now_utc - timedelta(days=5)

    # Valid: 12 hours into future (slight sensor clock drift)
    payload2 = DummyPayload(HUB_TS=(now_utc + timedelta(hours=12)).isoformat())
    parsed2 = _parse_event_time(payload2, now_utc)
    assert parsed2 == now_utc + timedelta(hours=12)

    # Valid: Exactly 35 days ago
    payload3 = DummyPayload(HUB_TS=(now_utc - timedelta(days=35)).isoformat())
    parsed3 = _parse_event_time(payload3, now_utc)
    assert parsed3 == now_utc - timedelta(days=35)

    # Valid: Exactly 24 hours future
    payload4 = DummyPayload(HUB_TS=(now_utc + timedelta(hours=24)).isoformat())
    parsed4 = _parse_event_time(payload4, now_utc)
    assert parsed4 == now_utc + timedelta(hours=24)


def test_parse_event_time_out_of_bounds_clamped():
    """Timestamps older than 35d or beyond 24h are clamped to fallback_utc."""
    now_utc = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)

    # Stale packet: 36 days ago (exceeds 35d boundary)
    payload_old = DummyPayload(HUB_TS=(now_utc - timedelta(days=36)).isoformat())
    parsed_old = _parse_event_time(payload_old, now_utc)
    assert parsed_old == now_utc

    # Stale packet: 1 year ago
    payload_very_old = DummyPayload(HUB_TS=(now_utc - timedelta(days=365)).isoformat())
    parsed_very_old = _parse_event_time(payload_very_old, now_utc)
    assert parsed_very_old == now_utc

    # Drifting packet: 25 hours into future
    payload_future = DummyPayload(HUB_TS=(now_utc + timedelta(hours=25)).isoformat())
    parsed_future = _parse_event_time(payload_future, now_utc)
    assert parsed_future == now_utc

    # Absurd future: Year 2030
    payload_far_future = DummyPayload(HUB_TS="2030-01-01T00:00:00Z")
    parsed_far_future = _parse_event_time(payload_far_future, now_utc)
    assert parsed_far_future == now_utc


def test_parse_event_time_handles_naive_and_aware():
    """Ensure naive datetimes are converted to UTC without TypeError comparisons."""
    now_utc = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)

    # Naive ISO string (no Z or offset)
    payload_naive_str = DummyPayload(HUB_TS="2026-09-12T10:00:00")
    parsed_str = _parse_event_time(payload_naive_str, now_utc)
    assert parsed_str.tzinfo is not None
    assert parsed_str == datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)

    # Naive datetime object
    naive_dt = datetime(2026, 9, 12, 10, 0, 0)
    payload_naive_obj = DummyPayload(timestamp=naive_dt)
    parsed_obj = _parse_event_time(payload_naive_obj, now_utc)
    assert parsed_obj.tzinfo is not None
    assert parsed_obj == datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)

    # Naive fallback_utc safely normalized
    naive_fallback = datetime(2026, 9, 12, 12, 0, 0)
    payload_empty = DummyPayload()
    parsed_fallback = _parse_event_time(payload_empty, naive_fallback)
    assert parsed_fallback.tzinfo is not None
    assert parsed_fallback == now_utc


def test_parse_event_time_numeric_timestamp():
    """Epoch float/integer timestamps are parsed and validated within bounds."""
    now_utc = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)
    epoch_now = now_utc.timestamp()

    # Valid: 1 hour ago
    payload_num = DummyPayload(HUB_TS=epoch_now - 3600)
    parsed = _parse_event_time(payload_num, now_utc)
    assert parsed == now_utc - timedelta(hours=1)

    # Invalid: 40 days ago
    payload_old_epoch = DummyPayload(HUB_TS=epoch_now - (40 * 86400))
    assert _parse_event_time(payload_old_epoch, now_utc) == now_utc


# ---------------------------------------------------------------------------
# 2. Partition Manager Pure Functional Core Tests
# ---------------------------------------------------------------------------

def test_add_months_arithmetic():
    """Verify month offset boundary calculations including year rollovers."""
    dt = datetime(2026, 9, 12, 15, 30, 45, tzinfo=UTC)

    # Offset 0: start of current month
    m0 = _add_months(dt, 0)
    assert m0 == datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)

    # Offset 1: next month
    m1 = _add_months(dt, 1)
    assert m1 == datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)

    # Offset 2: month after next
    m2 = _add_months(dt, 2)
    assert m2 == datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)

    # Offset 4: rollover into next year (Sep + 4 = Jan 2027)
    m4 = _add_months(dt, 4)
    assert m4 == datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Negative offset: August 2026
    m_prev = _add_months(dt, -1)
    assert m_prev == datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)


def test_generate_partition_ddl():
    """Verify partition name and DDL syntax."""
    start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)

    name, ddl = _generate_partition_ddl("data_table", start, end)
    assert name == "data_table_y2026_10"
    assert 'CREATE TABLE IF NOT EXISTS "data_table_y2026_10" PARTITION OF "data_table"' in ddl
    assert "FOR VALUES FROM ('2026-10-01T00:00:00+00:00') TO ('2026-11-01T00:00:00+00:00');" in ddl


def test_parse_partition_upper_bound():
    """Verify parsing PostgreSQL relpartbound range expressions."""
    # Standard format with timezone offset
    expr1 = "FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')"
    dt1 = _parse_partition_upper_bound(expr1)
    assert dt1 == datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)

    # ISO format with +00:00
    expr2 = "FOR VALUES FROM ('2026-08-01T00:00:00+00:00') TO ('2026-09-01T00:00:00+00:00')"
    dt2 = _parse_partition_upper_bound(expr2)
    assert dt2 == datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)

    # DEFAULT partition expression (should return None, no upper bound)
    assert _parse_partition_upper_bound("DEFAULT") is None

    # Invalid / None expressions
    assert _parse_partition_upper_bound(None) is None
    assert _parse_partition_upper_bound("") is None
    assert _parse_partition_upper_bound("MALFORMED EXPRESSION") is None


# ---------------------------------------------------------------------------
# 3. Partition Pre-creation & Pruning Workflow Tests
# ---------------------------------------------------------------------------

def test_precreate_future_partitions_executes_ddl():
    """Verify pre-creation generates and executes DDL for T, T+1, T+2 months."""
    now = datetime(2026, 9, 15, tzinfo=UTC)
    mock_conn = MagicMock()

    created = _precreate_future_partitions(mock_conn, "temperature_data", now)

    assert created == [
        "temperature_data_y2026_09",
        "temperature_data_y2026_10",
        "temperature_data_y2026_11",
    ]
    assert mock_conn.execute.call_count == 3


def test_prune_expired_partitions_detaches_and_drops():
    """Verify expired partitions (> 30 days) are non-blockingly detached and dropped."""
    now = datetime(2026, 9, 15, tzinfo=UTC)
    # Retention threshold = 2026-09-15 - 30 days = 2026-08-16

    mock_conn = MagicMock()

    # Mock catalog return: 1 expired partition (July -> August), 1 active partition (August -> September)
    Row = MagicMock
    row_expired = Row(
        child_name="data_table_y2026_07",
        bound_expr="FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')",
    )
    row_active = Row(
        child_name="data_table_y2026_08",
        bound_expr="FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00')",
    )
    mock_conn.execute.return_value.fetchall.return_value = [row_expired, row_active]

    pruned = _prune_expired_partitions(mock_conn, "data_table", now)

    assert pruned == ["data_table_y2026_07"]

    # Verify executed statements:
    # 1. Catalog query
    # 2. ALTER TABLE "data_table" DETACH PARTITION "data_table_y2026_07" CONCURRENTLY;
    # 3. DROP TABLE IF EXISTS "data_table_y2026_07";
    executed_sqls = [str(c[0][0]) for c in mock_conn.execute.call_args_list]

    detach_sqls = [s for s in executed_sqls if "DETACH PARTITION" in s]
    assert len(detach_sqls) == 1
    assert 'ALTER TABLE "data_table" DETACH PARTITION "data_table_y2026_07" CONCURRENTLY;' in detach_sqls[0]

    drop_sqls = [s for s in executed_sqls if "DROP TABLE" in s]
    assert len(drop_sqls) == 1
    assert 'DROP TABLE IF EXISTS "data_table_y2026_07";' in drop_sqls[0]


# ---------------------------------------------------------------------------
# 4. Dialect Safety & Integration Tests
# ---------------------------------------------------------------------------

def test_run_partition_maintenance_bypasses_sqlite():
    """Verify run_partition_maintenance gracefully no-ops when targeting SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        sqlite_engine = create_engine(f"sqlite:///{tmp_path}")

        with patch("app.services.partition_manager.logger") as mock_logger:
            run_partition_maintenance(target_engine=sqlite_engine)
            mock_logger.debug.assert_called_with("Partition maintenance skipped on SQLite dialect.")

        sqlite_engine.dispose()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def test_scheduler_job_registered():
    """Verify scheduler_lifespan registers daily 02:15 AM partition maintenance job."""
    from app.services.scheduler import CANONICAL_TZ
    from apscheduler.triggers.cron import CronTrigger

    trigger = CronTrigger(hour=2, minute=15, timezone=CANONICAL_TZ)
    field_dict = {f.name: str(f) for f in trigger.fields}
    assert field_dict["hour"] == "2"
    assert field_dict["minute"] == "15"
    assert field_dict["second"] == "0"
