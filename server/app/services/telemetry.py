# app/services/telemetry.py
from datetime import UTC
from typing import Any, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modelsv5 import ats_data, data_table, dev_table, temperature_data


def _format_ts(ts_dt: Any) -> Optional[str]:
    if not ts_dt:
        return None
    if hasattr(ts_dt, "tzinfo") and ts_dt.tzinfo is None:
        ts_dt = ts_dt.replace(tzinfo=UTC)
    return ts_dt.isoformat() if hasattr(ts_dt, "isoformat") else str(ts_dt)


def get_latest_readings_for_devices(
    db: Session,
    devices: list[dev_table],
) -> dict[str, dict[str, Any]]:
    """
    Fetches latest telemetry readings for a collection of devices in batch (O(1) queries).
    Leverages composite indexes on (dev_id, timestamp DESC) on telemetry tables.
    Returns a dict mapping dev_id -> latest_reading dict.
    """
    if not devices:
        return {}

    readings: dict[str, dict[str, Any]] = {}

    ts_ac_dev_ids = [d.dev_id for d in devices if (d.dev_type or "").upper() in ("TS", "AC", "ACC")]
    ats_dev_ids = [d.dev_id for d in devices if (d.dev_type or "").upper() == "ATS"]
    ac_dev_ids = [d.dev_id for d in devices if (d.dev_type or "").upper() in ("AC", "ACC")]

    # 1. Batched temperature_data for TS, AC, ACC
    if ts_ac_dev_ids:
        subq = (
            select(
                temperature_data.dev_id.label("dev_id"),
                func.max(temperature_data.timestamp).label("max_ts"),
            )
            .where(temperature_data.dev_id.in_(ts_ac_dev_ids))
            .group_by(temperature_data.dev_id)
            .subquery()
        )
        stmt = (
            select(temperature_data)
            .join(
                subq,
                (temperature_data.dev_id == subq.c.dev_id)
                & (temperature_data.timestamp == subq.c.max_ts),
            )
        )
        for row in db.execute(stmt).scalars().all():
            readings[row.dev_id] = {
                "timestamp": _format_ts(row.timestamp),
                "temp": row.temp,
                "humid": row.humid,
            }

    # 2. Batched ats_data for ATS
    if ats_dev_ids:
        subq = (
            select(
                ats_data.dev_id.label("dev_id"),
                func.max(ats_data.timestamp).label("max_ts"),
            )
            .where(ats_data.dev_id.in_(ats_dev_ids))
            .group_by(ats_data.dev_id)
            .subquery()
        )
        stmt = (
            select(ats_data)
            .join(
                subq,
                (ats_data.dev_id == subq.c.dev_id)
                & (ats_data.timestamp == subq.c.max_ts),
            )
        )
        for row in db.execute(stmt).scalars().all():
            readings[row.dev_id] = {
                "timestamp": _format_ts(row.timestamp),
                "state": row.state,
                "pln": row.pln,
                "genset": row.genset,
                "aki": row.aki,
                "auto_mode": row.auto_mode,
                "emergency": row.emergency,

                #Legacy fields, for compatibility with older database entries. These fields may not be present in newer entries.
                "rem_hour": row.rem_hour,
                "rem_min": row.rem_min,
                "rem_sec": row.rem_sec,

                #New fields, for compatibility with newer database entries. These fields may not be present in older entries.
                "pln_relay": row.pln_relay,
                "gen_relay": row.gen_relay,
                "alarm": row.alarm,
                "warmup": row.warmup,
            }

    # 3. Batched data_table for AC payload merge and fallback devices
    need_dt_ids = set(ac_dev_ids) | {d.dev_id for d in devices if d.dev_id not in readings}
    if need_dt_ids:
        subq = (
            select(
                data_table.dev_id.label("dev_id"),
                func.max(data_table.timestamp).label("max_ts"),
            )
            .where(data_table.dev_id.in_(list(need_dt_ids)))
            .group_by(data_table.dev_id)
            .subquery()
        )
        stmt = (
            select(data_table)
            .join(
                subq,
                (data_table.dev_id == subq.c.dev_id)
                & (data_table.timestamp == subq.c.max_ts),
            )
        )
        for row in db.execute(stmt).scalars().all():
            if row.dev_id in ac_dev_ids and row.payload and isinstance(row.payload, dict):
                p = row.payload
                cur = readings.get(row.dev_id)
                if cur is None:
                    cur = {}
                    cur_ts = _format_ts(row.timestamp)
                    if cur_ts:
                        cur["timestamp"] = cur_ts
                    readings[row.dev_id] = cur
                for k in ("AC1_POWER", "AC1_TEMP", "AC2_POWER", "AC2_TEMP", "IS_AC1_ON", "IS_AC2_ON", "TEMP", "HUMID"):
                    val = p.get(k)
                    if val is None:
                        val = p.get(k.lower())
                    if val is not None:
                        if "POWER" in k and isinstance(val, str):
                            val = val.upper()
                        cur[k] = val
                        cur[k.lower()] = val
            elif row.dev_id not in readings or readings[row.dev_id] is None:
                p = row.payload or {}
                payload_copy = dict(p) if isinstance(p, dict) else {}
                if "timestamp" not in payload_copy and row.timestamp:
                    payload_copy["timestamp"] = _format_ts(row.timestamp)
                readings[row.dev_id] = payload_copy

    return readings
