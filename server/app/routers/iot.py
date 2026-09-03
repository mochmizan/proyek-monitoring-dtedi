# app/routers/iot.py
from datetime import UTC, datetime
import logging
from typing import Any, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.dependencies import verify_hub_identity
from app.services.alert_engine import evaluate_device_thresholds
from app.services.presence import resolve_offline_on_telemetry
from databasev5 import get_db
from modelsv5 import ats_data, data_table, dev_table, hub_table, temperature_data
from schemasv5 import (
    ATSData,
    IotBatchRequest,
    IotBatchResponse,
    IotPayload,
    TSData,
    UnapprovedDeviceAlert,
)

router = APIRouter(tags=["iot"])


def _parse_event_time(item: Any, fallback_utc: datetime) -> datetime:
    """Extract event timestamp from payload (HUB_TS, _hub_created_at, or timestamp).
    Preserves microsecond precision and ensures UTC timezone."""
    hub_ts_raw = None
    try:
        if hasattr(item, "HUB_TS") and getattr(item, "HUB_TS") is not None:
            hub_ts_raw = getattr(item, "HUB_TS")
        elif hasattr(item, "hub_created_at") and getattr(item, "hub_created_at") is not None:
            hub_ts_raw = getattr(item, "hub_created_at")
        elif hasattr(item, "timestamp") and getattr(item, "timestamp") is not None:
            hub_ts_raw = getattr(item, "timestamp")
        else:
            extra = getattr(item, "__pydantic_extra__", None)
            if isinstance(extra, dict):
                hub_ts_raw = extra.get("_hub_created_at") or extra.get("HUB_TS") or extra.get("timestamp")
            if hub_ts_raw is None and hasattr(item, "model_dump"):
                _dump = item.model_dump(mode="json", by_alias=True)
                hub_ts_raw = _dump.get("_hub_created_at") or _dump.get("HUB_TS") or _dump.get("hub_created_at") or _dump.get("timestamp")
            elif hub_ts_raw is None and isinstance(item, dict):
                hub_ts_raw = item.get("_hub_created_at") or item.get("HUB_TS") or item.get("hub_created_at") or item.get("timestamp")
    except Exception:
        hub_ts_raw = None

    if hub_ts_raw is not None:
        try:
            if isinstance(hub_ts_raw, (int, float)):
                return datetime.fromtimestamp(float(hub_ts_raw), tz=UTC)
            elif isinstance(hub_ts_raw, str):
                try:
                    dt = datetime.fromisoformat(hub_ts_raw)
                    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
                except ValueError:
                    return datetime.fromtimestamp(float(hub_ts_raw), tz=UTC)
            elif isinstance(hub_ts_raw, datetime):
                return hub_ts_raw if hub_ts_raw.tzinfo is not None else hub_ts_raw.replace(tzinfo=UTC)
        except Exception:
            pass

    return fallback_utc


def _generate_deterministic_id(dev_id: str, ts: datetime) -> str:
    """Generate deterministic UUID from device id and timestamp to support replay idempotency."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{dev_id}:{ts.isoformat()}"))


def bulk_insert_or_ignore(
    session: Session,
    model: Any,
    records: list[dict],
    index_elements: list[str],
    chunk_size: int = 500,
) -> int:
    """Dialect-agnostic bulk insertion with ON CONFLICT DO NOTHING (PostgreSQL & SQLite WAL).
    Chunked by 500 to guarantee compliance with SQLite variable binding limits."""
    if not records:
        return 0

    dialect_name = session.get_bind().dialect.name
    total_rowcount = 0

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import insert
            try:
                stmt = pg_insert(model).values(chunk).on_conflict_do_nothing(
                    index_elements=index_elements
                )
                res = session.execute(stmt)
                count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
                total_rowcount += count
            except OperationalError as err:
                tbl_name = getattr(model, "__tablename__", str(model))
                logging.warning(
                    f"OperationalError in bulk_insert_or_ignore on {tbl_name}: {err}. "
                    "Falling back to standard insert."
                )
                res = session.execute(insert(model).values(chunk))
                count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
                total_rowcount += count
        elif dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            try:
                stmt = sqlite_insert(model).values(chunk).on_conflict_do_nothing(
                    index_elements=index_elements
                )
                res = session.execute(stmt)
                count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
                total_rowcount += count
            except OperationalError as err:
                tbl_name = getattr(model, "__tablename__", str(model))
                logging.warning(
                    f"OperationalError in bulk_insert_or_ignore on {tbl_name} (possible missing unique index): {err}. "
                    "Falling back to standard insert."
                )
                from sqlalchemy import insert
                try:
                    fallback_stmt = sqlite_insert(model).values(chunk).prefix_with("OR IGNORE")
                    res = session.execute(fallback_stmt)
                    count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
                    total_rowcount += count
                except Exception as fallback_err:
                    logging.warning(
                        f"Fallback OR IGNORE failed on {tbl_name} ({fallback_err}), attempting plain insert."
                    )
                    res = session.execute(insert(model).values(chunk))
                    count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
                    total_rowcount += count
        else:
            from sqlalchemy import insert
            stmt = insert(model).values(chunk)
            res = session.execute(stmt)
            count = res.rowcount if (res.rowcount is not None and res.rowcount >= 0) else len(chunk)
            total_rowcount += count

    return total_rowcount


@router.post("/api/iot/unapproved")
@limiter.limit("60/minute")
def receive_unapproved_alert(
    request: Request,
    payload: UnapprovedDeviceAlert,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    try:
        exist = db.get(dev_table, payload.DEV_ID)
        now_utc = datetime.now(UTC)
        if exist is None:
            new_pending_device = dev_table(
                dev_id=payload.DEV_ID,
                dev_name=payload.DEV_NAME,
                dev_type=payload.DEV_TYPE,
                hub_id=hub.hub_id,
                is_active=False,
                created_at=now_utc,
            )
            db.add(new_pending_device)
            db.commit()
            return {"status": "registered_as_pending"}
        else:
            if not exist.is_active:
                exist.created_at = now_utc
                exist.hub_id = hub.hub_id
                if payload.DEV_NAME and (not exist.dev_name or exist.dev_name == exist.dev_id):
                    exist.dev_name = payload.DEV_NAME
                if payload.DEV_TYPE and not exist.dev_type:
                    exist.dev_type = payload.DEV_TYPE
                db.commit()
            return {"status": "already_exists"}
    except Exception:
        logging.exception("Exception in receive_unapproved_alert")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/api/iot")
@limiter.limit("120/minute")
def receive_iot(
    request: Request,
    device: IotPayload,
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    """Single telemetry ingestion handler executing in a single atomic commit transaction.
    Uses deterministic ID generation and idempotent bulk insert logic."""
    try:
        registered_device = db.get(dev_table, device.DEV_ID)
        if not registered_device or not registered_device.is_active:
            raise HTTPException(status_code=403, detail="Device not authorized")

        if registered_device.hub_id != hub.hub_id:
            logging.warning(
                f"Security warning: Hub '{hub.hub_id}' attempted to ingest telemetry for device '{device.DEV_ID}' "
                f"belonging to hub '{registered_device.hub_id}'"
            )
            raise HTTPException(status_code=403, detail="Device does not belong to this hub")

        now_utc = datetime.now(UTC)
        event_time = _parse_event_time(device, now_utc)
        data_id = _generate_deterministic_id(device.DEV_ID, event_time)

        resolve_offline_on_telemetry(db, registered_device, now_utc)

        dev_type = getattr(device, "DEV_TYPE", None)
        if isinstance(device, TSData) or dev_type == "TS":
            records = [{
                "data_id": data_id,
                "dev_id": device.DEV_ID,
                "timestamp": event_time,
                "temp": getattr(device, "TEMP", None),
                "humid": getattr(device, "HUMID", None),
            }]
            bulk_insert_or_ignore(db, temperature_data, records, ["dev_id", "timestamp"])
        elif isinstance(device, ATSData) or dev_type == "ATS":
            records = [{
                "data_id": data_id,
                "dev_id": device.DEV_ID,
                "timestamp": event_time,
                "state": getattr(device, "STATE", "unknown"),
                "pln": float(getattr(device, "PLN", 0.0) or 0.0),
                "genset": float(getattr(device, "GENSET", 0.0) or 0.0),
                "aki": float(getattr(device, "AKI", 0.0) or 0.0),
                "rem_hour": float(getattr(device, "REM_HOUR", 0.0) or 0.0),
                "rem_min": float(getattr(device, "REM_MIN", 0.0) or 0.0),
                "rem_sec": float(getattr(device, "REM_SEC", 0.0) or 0.0),
                "auto_mode": bool(getattr(device, "AUTO_MODE", False)),
                "emergency": bool(getattr(device, "EMERGENCY", False)),
            }]
            bulk_insert_or_ignore(db, ats_data, records, ["dev_id", "timestamp"])
        else:
            records = [{
                "data_id": data_id,
                "dev_id": device.DEV_ID,
                "dev_name": getattr(device, "DEV_NAME", device.DEV_ID),
                "timestamp": event_time,
                "payload": device.model_dump(mode="json"),
            }]
            bulk_insert_or_ignore(db, data_table, records, ["dev_id", "timestamp"])

            payload_dict = device.model_dump(mode="json", by_alias=True)
            if ("TEMP" in payload_dict and payload_dict["TEMP"] is not None) or ("HUMID" in payload_dict and payload_dict["HUMID"] is not None):
                temp_val = float(payload_dict["TEMP"]) if "TEMP" in payload_dict and payload_dict["TEMP"] is not None else None
                humid_val = float(payload_dict["HUMID"]) if "HUMID" in payload_dict and payload_dict["HUMID"] is not None else None
                records_temp = [{
                    "data_id": data_id,
                    "dev_id": device.DEV_ID,
                    "timestamp": event_time,
                    "temp": temp_val,
                    "humid": humid_val,
                }]
                bulk_insert_or_ignore(db, temperature_data, records_temp, ["dev_id", "timestamp"])

        payload_dict = device.model_dump(mode="json", by_alias=True)
        evaluate_device_thresholds(db=db, dev=registered_device, payload=payload_dict, timestamp=event_time)

        # Single atomic commit: Heartbeat + Telemetry + Presence + Alerts
        db.commit()
        return {"status": "received"}

    except HTTPException:
        raise
    except Exception:
        logging.exception("Exception in receive_iot")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record data")


@router.post("/api/iot/batch", response_model=IotBatchResponse)
@limiter.limit("60/minute")
def receive_iot_batch(
    request: Request,
    payload: Union[IotBatchRequest, list[IotPayload]],
    hub: hub_table = Depends(verify_hub_identity),
    db: Session = Depends(get_db),
):
    """High-throughput atomic batch telemetry ingestion endpoint.
    Ingests up to 1000 items with ON CONFLICT DO NOTHING idempotency.
    Suppresses alert bursts by evaluating threshold alerts and presence ONLY once per device on its latest reading."""
    if isinstance(payload, IotBatchRequest):
        items = payload.items
    elif isinstance(payload, list):
        items = payload
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payload must be an IotBatchRequest object or a list of items",
        )

    if not items or len(items) > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch size must be between 1 and 1000 items",
        )

    try:
        now_utc = datetime.now(UTC)

        # 1. Bulk query active approved devices
        unique_dev_ids = {item.DEV_ID for item in items}
        active_devices = (
            db.query(dev_table)
            .filter(dev_table.dev_id.in_(unique_dev_ids), dev_table.is_active == True)  # noqa: E712
            .all()
        )
        device_map = {d.dev_id: d for d in active_devices}

        records_temp: list[dict] = []
        records_ats: list[dict] = []
        records_data: list[dict] = []

        seen_temp: set[tuple[str, datetime]] = set()
        seen_ats: set[tuple[str, datetime]] = set()
        seen_data: set[tuple[str, datetime]] = set()

        # Track latest point per device for deduplicated alert & presence evaluation
        latest_reading_per_dev: dict[str, tuple[datetime, dict, dev_table]] = {}
        ignored_count = 0

        for item in items:
            if item.DEV_ID not in device_map:
                ignored_count += 1
                continue

            dev_obj = device_map[item.DEV_ID]
            if dev_obj.hub_id != hub.hub_id:
                logging.warning(
                    f"Security warning: Hub '{hub.hub_id}' attempted to ingest batch telemetry for device '{item.DEV_ID}' "
                    f"belonging to hub '{dev_obj.hub_id}'"
                )
                ignored_count += 1
                continue

            event_time = _parse_event_time(item, now_utc)
            data_id = _generate_deterministic_id(item.DEV_ID, event_time)

            # Update latest reading per device
            if (item.DEV_ID not in latest_reading_per_dev) or (event_time > latest_reading_per_dev[item.DEV_ID][0]):
                latest_payload = item.model_dump(mode="json", by_alias=True)
                latest_reading_per_dev[item.DEV_ID] = (event_time, latest_payload, dev_obj)

            key = (item.DEV_ID, event_time)
            dev_type = getattr(item, "DEV_TYPE", None)

            if isinstance(item, TSData) or dev_type == "TS":
                if key not in seen_temp:
                    seen_temp.add(key)
                    records_temp.append({
                        "data_id": data_id,
                        "dev_id": item.DEV_ID,
                        "timestamp": event_time,
                        "temp": getattr(item, "TEMP", None),
                        "humid": getattr(item, "HUMID", None),
                    })
            elif isinstance(item, ATSData) or dev_type == "ATS":
                if key not in seen_ats:
                    seen_ats.add(key)
                    records_ats.append({
                        "data_id": data_id,
                        "dev_id": item.DEV_ID,
                        "timestamp": event_time,
                        "state": getattr(item, "STATE", "unknown"),
                        "pln": float(getattr(item, "PLN", 0.0) or 0.0),
                        "genset": float(getattr(item, "GENSET", 0.0) or 0.0),
                        "aki": float(getattr(item, "AKI", 0.0) or 0.0),
                        "rem_hour": float(getattr(item, "REM_HOUR", 0.0) or 0.0),
                        "rem_min": float(getattr(item, "REM_MIN", 0.0) or 0.0),
                        "rem_sec": float(getattr(item, "REM_SEC", 0.0) or 0.0),
                        "auto_mode": bool(getattr(item, "AUTO_MODE", False)),
                        "emergency": bool(getattr(item, "EMERGENCY", False)),
                    })
            else:
                if key not in seen_data:
                    seen_data.add(key)
                    records_data.append({
                        "data_id": data_id,
                        "dev_id": item.DEV_ID,
                        "dev_name": getattr(item, "DEV_NAME", item.DEV_ID),
                        "timestamp": event_time,
                        "payload": item.model_dump(mode="json"),
                    })

                p_dict = item.model_dump(mode="json", by_alias=True)
                if ("TEMP" in p_dict and p_dict["TEMP"] is not None) or ("HUMID" in p_dict and p_dict["HUMID"] is not None):
                    if key not in seen_temp:
                        seen_temp.add(key)
                        records_temp.append({
                            "data_id": data_id,
                            "dev_id": item.DEV_ID,
                            "timestamp": event_time,
                            "temp": float(p_dict["TEMP"]) if "TEMP" in p_dict and p_dict["TEMP"] is not None else None,
                            "humid": float(p_dict["HUMID"]) if "HUMID" in p_dict and p_dict["HUMID"] is not None else None,
                        })

        # 2. Bulk inserts with dialect-specific ON CONFLICT DO NOTHING
        inserted_temp = bulk_insert_or_ignore(db, temperature_data, records_temp, ["dev_id", "timestamp"])
        inserted_ats = bulk_insert_or_ignore(db, ats_data, records_ats, ["dev_id", "timestamp"])
        inserted_data = bulk_insert_or_ignore(db, data_table, records_data, ["dev_id", "timestamp"])
        total_ingested = inserted_temp + inserted_ats + inserted_data

        # 3. Deduplicated Presence & Alert Evaluation (Latest reading only)
        for dev_id, (latest_ts, latest_payload, dev_obj) in latest_reading_per_dev.items():
            resolve_offline_on_telemetry(db, dev_obj, now_utc)
            evaluate_device_thresholds(db=db, dev=dev_obj, payload=latest_payload, timestamp=latest_ts)

        # 4. Single atomic commit: Heartbeat + Bulk Telemetry + Presence + Alerts
        db.commit()

        return IotBatchResponse(
            status="received",
            processed_count=len(items),
            ingested_count=total_ingested,
            ignored_count=ignored_count,
        )

    except HTTPException:
        raise
    except Exception:
        logging.exception("Exception in receive_iot_batch")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record batch data")

