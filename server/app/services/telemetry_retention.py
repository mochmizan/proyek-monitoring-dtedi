import logging
import threading
from calendar import monthrange
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from databasev5 import SessionLocal
from modelsv5 import (
    ats_data,
    ats_daily,
    ats_hourly,
    ats_monthly,
    temperature_data,
    temperature_daily,
    temperature_hourly,
    temperature_monthly,
)

logger = logging.getLogger(__name__)
_sqlite_lock = threading.Lock()
_ADVISORY_LOCK_ID = 0x534D5342524554
MAX_BUCKETS_PER_STAGE = 200


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _bucket_start(value: datetime, resolution: str) -> datetime:
    value = _as_utc(value)
    if resolution == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if resolution == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _metric_values(rows, metrics: tuple[str, ...], raw: bool) -> dict:
    values: dict = {}
    for metric in metrics:
        if raw:
            samples = [float(getattr(row, metric)) for row in rows if getattr(row, metric) is not None]
            total, count = sum(samples), len(samples)
            minimum, maximum = (min(samples), max(samples)) if samples else (None, None)
        else:
            total = sum(float(getattr(row, f"{metric}_sum")) for row in rows)
            count = sum(int(getattr(row, f"{metric}_count")) for row in rows)
            minima = [getattr(row, f"{metric}_min") for row in rows if getattr(row, f"{metric}_min") is not None]
            maxima = [getattr(row, f"{metric}_max") for row in rows if getattr(row, f"{metric}_max") is not None]
            minimum, maximum = (min(minima) if minima else None, max(maxima) if maxima else None)
        values.update({
            f"{metric}_sum": total,
            f"{metric}_count": count,
            f"{metric}_avg": total / count if count else None,
            f"{metric}_min": minimum,
            f"{metric}_max": maximum,
        })
    return values


def _aggregate(rows, kind: str, raw: bool) -> dict:
    values = _metric_values(rows, ("temp", "humid") if kind == "temperature" else ("pln", "genset", "aki"), raw)
    if kind == "ats":
        first_states = [row.state if raw else row.first_state for row in rows]
        last_states = [row.state if raw else row.last_state for row in rows]
        first_emergencies = [bool(row.emergency) if raw else row.first_emergency for row in rows]
        last_emergencies = [bool(row.emergency) if raw else row.last_emergency for row in rows]
        state_changes = 0 if raw else sum(row.state_change_count for row in rows)
        emergency_events = 0 if raw else sum(row.emergency_event_count for row in rows)
        for index in range(len(rows)):
            if index and last_states[index - 1] != first_states[index]:
                state_changes += 1
            if first_emergencies[index] and (index == 0 or not last_emergencies[index - 1]):
                emergency_events += 1
        values.update({
            "first_state": first_states[0], "last_state": last_states[-1],
            "first_emergency": first_emergencies[0], "last_emergency": last_emergencies[-1],
            "state_change_count": state_changes, "emergency_event_count": emergency_events,
        })
    return values


def _upsert(db, target, values: dict, metrics: tuple[str, ...], kind: str) -> None:
    dialect = db.get_bind().dialect.name
    insert = pg_insert(target) if dialect == "postgresql" else sqlite_insert(target)
    stmt = insert.values(**values)
    excluded = stmt.excluded
    updates = {}
    for metric in metrics:
        new_sum = getattr(target, f"{metric}_sum") + getattr(excluded, f"{metric}_sum")
        new_count = getattr(target, f"{metric}_count") + getattr(excluded, f"{metric}_count")
        updates.update({
            f"{metric}_sum": new_sum,
            f"{metric}_count": new_count,
            f"{metric}_avg": new_sum / func.nullif(new_count, 0),
            f"{metric}_min": func.coalesce(func.min(getattr(target, f"{metric}_min"), getattr(excluded, f"{metric}_min")) if dialect == "sqlite" else func.least(getattr(target, f"{metric}_min"), getattr(excluded, f"{metric}_min")), getattr(target, f"{metric}_min"), getattr(excluded, f"{metric}_min")),
            f"{metric}_max": func.coalesce(func.max(getattr(target, f"{metric}_max"), getattr(excluded, f"{metric}_max")) if dialect == "sqlite" else func.greatest(getattr(target, f"{metric}_max"), getattr(excluded, f"{metric}_max")), getattr(target, f"{metric}_max"), getattr(excluded, f"{metric}_max")),
        })
    if kind == "ats":
        updates.update({
            "last_state": excluded.last_state,
            "last_emergency": excluded.last_emergency,
            "state_change_count": target.state_change_count + excluded.state_change_count + func.cast(target.last_state != excluded.first_state, target.state_change_count.type),
            "emergency_event_count": target.emergency_event_count + excluded.emergency_event_count - func.cast((target.last_emergency == True) & (excluded.first_emergency == True), target.emergency_event_count.type),  # noqa: E712
        })
    db.execute(stmt.on_conflict_do_update(index_elements=["dev_id", "bucket_start"], set_=updates))


def _run_stage(db, source, target, kind: str, source_resolution: str, target_resolution: str, cutoff: datetime) -> int:
    time_col = source.timestamp if source_resolution == "raw" else source.bucket_start
    candidates = db.query(source.dev_id, time_col).filter(time_col < cutoff).order_by(time_col).limit(MAX_BUCKETS_PER_STAGE * 32).all()
    buckets = []
    seen = set()
    for dev_id, timestamp in candidates:
        key = (dev_id, _bucket_start(timestamp, target_resolution))
        if key not in seen:
            seen.add(key)
            buckets.append(key)
        if len(buckets) == MAX_BUCKETS_PER_STAGE:
            break
    processed = 0
    metrics = ("temp", "humid") if kind == "temperature" else ("pln", "genset", "aki")
    for dev_id, start in buckets:
        end = start + timedelta(hours=1) if target_resolution == "hour" else start + timedelta(days=1) if target_resolution == "day" else _shift_months(start, 1)
        rows = db.query(source).filter(source.dev_id == dev_id, time_col >= start, time_col < end, time_col < cutoff).order_by(time_col).all()
        if not rows:
            continue
        values = {"dev_id": dev_id, "bucket_start": start, **_aggregate(rows, kind, source_resolution == "raw")}
        try:
            _upsert(db, target, values, metrics, kind)
            db.query(source).filter(source.dev_id == dev_id, time_col >= start, time_col < end, time_col < cutoff).delete(synchronize_session=False)
            db.commit()
            processed += 1
        except Exception:
            db.rollback()
            raise
    return processed


def run_telemetry_retention(now: datetime | None = None) -> dict[str, int]:
    now = _as_utc(now or datetime.now(UTC))
    raw_cutoff = _bucket_start(now - timedelta(days=31), "hour")
    hourly_cutoff = _bucket_start(_shift_months(now, -3), "day")
    daily_cutoff = _bucket_start(_shift_months(now, -12), "month")
    db = SessionLocal()
    postgres = db.get_bind().dialect.name == "postgresql"
    acquired = False
    try:
        if postgres:
            acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_ID}).scalar())
            if not acquired:
                return {}
        else:
            acquired = _sqlite_lock.acquire(blocking=False)
            if not acquired:
                return {}
        stages = (
            (temperature_data, temperature_hourly, "temperature", "raw", "hour", raw_cutoff),
            (ats_data, ats_hourly, "ats", "raw", "hour", raw_cutoff),
            (temperature_hourly, temperature_daily, "temperature", "hour", "day", hourly_cutoff),
            (ats_hourly, ats_daily, "ats", "hour", "day", hourly_cutoff),
            (temperature_daily, temperature_monthly, "temperature", "day", "month", daily_cutoff),
            (ats_daily, ats_monthly, "ats", "day", "month", daily_cutoff),
        )
        return {stage[1].__tablename__: _run_stage(db, *stage) for stage in stages}
    except Exception:
        logger.exception("Tiered telemetry retention failed")
        return {}
    finally:
        if postgres and acquired:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_ID})
        elif not postgres and acquired:
            _sqlite_lock.release()
        db.close()
