# app/services/presence.py — device/hub presence & offline/online state handling
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from databasev5 import SessionLocal
from modelsv5 import dev_table, event_log, hub_table, rooms

logger = logging.getLogger(__name__)

HUB_ONLINE_WINDOW_SECONDS = 25
DEVICE_OFFLINE_WINDOW_SECONDS = 25
PRESENCE_INTERVAL_SECONDS = 5


def evaluate_device_presence_batch() -> None:
    """Periodic background task running every PRESENCE_INTERVAL_SECONDS.
    Evaluates active device state transitions in-memory, batches offline alert
    insertions and online recoveries, and prunes stale unapproved devices older than 25s.
    Runs in an isolated scoped SessionLocal() with rollback protection.
    """
    db = SessionLocal()
    try:
        now_utc = datetime.now(UTC)
        cutoff = now_utc - timedelta(seconds=DEVICE_OFFLINE_WINDOW_SECONDS)

        # 1. Bulk fetch all active devices eagerly loading room
        active_devices = (
            db.execute(
                select(dev_table)
                .options(selectinload(dev_table.room))
                .where(dev_table.is_active == True)  # noqa: E712
            )
            .scalars()
            .all()
        )

        # 2. Bulk fetch all currently unresolved offline alerts
        open_alerts = (
            db.execute(
                select(event_log).where(
                    event_log.alarm == "DEVICE_OFFLINE",
                    event_log.resolved_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        open_alerts_by_dev: dict[str, list[event_log]] = defaultdict(list)
        for a in open_alerts:
            if a.dev_id:
                open_alerts_by_dev[a.dev_id].append(a)

        has_state_changes = False

        for dev in active_devices:
            d_seen = (
                dev.last_seen if (dev.last_seen and dev.last_seen.tzinfo is not None)
                else (dev.last_seen.replace(tzinfo=UTC) if dev.last_seen else None)
            )
            online = bool(d_seen and d_seen >= cutoff)

            # Online -> Offline transition
            if not online and dev.last_status == "online":
                dev.last_status = "offline"
                has_state_changes = True
                if dev.dev_id not in open_alerts_by_dev:
                    dev_label = dev.dev_name or dev.dev_id
                    room_name = dev.room.name if dev.room else "Unassigned"
                    off_alert = event_log(
                        event_id=uuid.uuid4().hex,
                        alarm="DEVICE_OFFLINE",
                        timestamp=now_utc,
                        message=f"Device '{dev_label}' ({dev.dev_id}) in '{room_name}' went OFFLINE (No signal for > 25s).",
                        dev_id=dev.dev_id,
                        room_id=dev.room_id,
                        metric="connectivity",
                        severity="warning",
                        value=0.0,
                        threshold=1.0,
                        resolved_at=None,
                    )
                    db.add(off_alert)
                    open_alerts_by_dev[dev.dev_id].append(off_alert)

            # Offline -> Online transition
            elif online and dev.last_status != "online":
                dev.last_status = "online"
                has_state_changes = True
                if dev.dev_id in open_alerts_by_dev:
                    for alert in open_alerts_by_dev[dev.dev_id]:
                        alert.resolved_at = now_utc
                    del open_alerts_by_dev[dev.dev_id]

        # 3. Bulk prune stale unapproved/pending devices in a single core statement
        prune_stmt = delete(dev_table).where(
            dev_table.is_active == False,  # noqa: E712
            dev_table.room_id.is_(None),
            dev_table.created_at < cutoff,
        )
        prune_res = db.execute(prune_stmt)
        if prune_res.rowcount and prune_res.rowcount > 0:
            has_state_changes = True

        if has_state_changes:
            db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Error during background presence evaluation: {e}")
    finally:
        db.close()


def is_online(last_seen, cutoff) -> bool:
    if not last_seen:
        return False
    ls = last_seen if last_seen.tzinfo is not None else last_seen.replace(tzinfo=UTC)
    return ls >= cutoff


def update_device_presence_on_list(db: Session, now_utc: datetime, cutoff: datetime):
    """Scan active devices and generate DEVICE_OFFLINE alerts + update last_status.
    Returns True if any state changed.
    """
    active_devices = db.query(dev_table).filter(dev_table.is_active == True).all()  # noqa: E712
    has_state_changes = False
    for d in active_devices:
        last_seen_dt = None
        if d.last_seen:
            last_seen_dt = d.last_seen if d.last_seen.tzinfo is not None else d.last_seen.replace(tzinfo=UTC)
        online = bool(last_seen_dt and last_seen_dt >= cutoff)

        if not online and d.last_status == "online":
            d.last_status = "offline"
            has_state_changes = True
            open_alert = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == d.dev_id,
                    event_log.alarm == "DEVICE_OFFLINE",
                    event_log.resolved_at.is_(None),
                )
                .first()
            )
            if not open_alert:
                dev_label = d.dev_name or d.dev_id
                room_obj = db.get(rooms, d.room_id) if d.room_id else None
                room_name = room_obj.name if room_obj else "Unassigned"
                off_alert = event_log(
                    event_id=uuid.uuid4().hex,
                    alarm="DEVICE_OFFLINE",
                    timestamp=now_utc,
                    message=f"Device '{dev_label}' ({d.dev_id}) in '{room_name}' went OFFLINE (No signal for > 25s).",
                    dev_id=d.dev_id,
                    room_id=d.room_id,
                    metric="connectivity",
                    severity="warning",
                    value=0.0,
                    threshold=1.0,
                    resolved_at=None,
                )
                db.add(off_alert)
        elif online and d.last_status != "online":
            d.last_status = "online"
            has_state_changes = True
    if has_state_changes:
        db.commit()
    return has_state_changes


def prune_stale_pending(db: Session, cutoff: datetime):
    stale_pending = (
        db.query(dev_table)
        .filter(
            dev_table.is_active == False,  # noqa: E712
            dev_table.room_id.is_(None),
            dev_table.created_at < cutoff,
        )
        .all()
    )
    if stale_pending:
        for st in stale_pending:
            db.delete(st)
        db.commit()


def resolve_offline_on_telemetry(db: Session, device, now_utc: datetime):
    """Called on successful telemetry: mark device online and resolve DEVICE_OFFLINE alerts."""
    was_offline = device.last_status == "offline"
    device.last_seen = now_utc
    device.last_status = "online"
    if was_offline:
        open_offline_alerts = (
            db.query(event_log)
            .filter(
                event_log.dev_id == device.dev_id,
                event_log.alarm == "DEVICE_OFFLINE",
                event_log.resolved_at.is_(None),
            )
            .all()
        )
        if open_offline_alerts:
            for alert in open_offline_alerts:
                alert.resolved_at = now_utc
            dev_label = device.dev_name or device.dev_id
            room_obj = db.get(rooms, device.room_id) if device.room_id else None
            room_name = room_obj.name if room_obj else "Unassigned"
            online_event = event_log(
                event_id=uuid.uuid4().hex,
                alarm="DEVICE_ONLINE",
                timestamp=now_utc,
                message=f"Device '{dev_label}' ({device.dev_id}) in '{room_name}' is back ONLINE.",
                dev_id=device.dev_id,
                room_id=device.room_id,
                metric="connectivity",
                severity="info",
                value=1.0,
                threshold=1.0,
                resolved_at=now_utc,
            )
            db.add(online_event)
