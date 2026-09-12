# app/services/scheduler.py — APScheduler BackgroundScheduler for flexible ATS scheduling
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[BackgroundScheduler] = None

# APScheduler defaults per spec
JOB_DEFAULTS = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}
CANONICAL_TZ = "Asia/Jakarta"


def _validate_cron_expr(cron_expr: str, tz: str = CANONICAL_TZ) -> None:
    """Validate 5-field cron via CronTrigger.from_crontab. Raises ValueError on invalid."""
    if not cron_expr or not cron_expr.strip():
        raise ValueError("cron_expr is required")
    stripped = cron_expr.strip()
    # Reject non-standard shortcuts like @reboot, @daily etc
    if stripped.startswith("@"):
        raise ValueError(f"Unsupported cron shortcut '{stripped}'; use 5-field cron")
    parts = stripped.split()
    if len(parts) != 5:
        raise ValueError(f"cron_expr must have 5 fields, got {len(parts)}: '{cron_expr}'")
    try:
        # timezone-aware trigger creation validates expression
        CronTrigger.from_crontab(stripped, timezone=tz)
    except Exception as e:
        raise ValueError(f"Invalid cron_expr '{cron_expr}': {e}") from e


def cron_kwargs(cron_expr: str, tz: str = CANONICAL_TZ) -> dict:
    """Return kwargs for scheduler.add_job via CronTrigger.from_crontab."""
    _validate_cron_expr(cron_expr, tz)
    # Use from_crontab to get trigger, but add_job expects trigger instance via CronTrigger
    # We'll pass trigger object directly in add_job; this helper returns dict with trigger key
    trigger = CronTrigger.from_crontab(cron_expr.strip(), timezone=tz)
    return {"trigger": trigger}


def get_next_runs(cron_expr: str, tz: str = CANONICAL_TZ, count: int = 3) -> list[datetime]:
    """Compute next fire times for preview. Returns list of aware datetimes."""
    try:
        trigger = CronTrigger.from_crontab(cron_expr.strip(), timezone=tz)
    except Exception:
        return []
    # Need to walk forward from now in given tz
    try:
        from zoneinfo import ZoneInfo
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = None
    now = datetime.now(tzinfo) if tzinfo else datetime.now(UTC)
    runs: list[datetime] = []
    current = now
    for _ in range(count):
        nxt = trigger.get_next_fire_time(None, current)
        if nxt is None:
            break
        # Ensure timezone aware
        runs.append(nxt)
        # Move slightly past nxt to get following
        current = nxt
        # apscheduler expects previous_fire_time and now; second arg is now
        # For sequential, pass nxt as previous via next iteration shifting
        # Actually get_next_fire_time(prev, now) — we want successive
        # So feed nxt as previous in next loop
        # Workaround: keep advancing by 1 second to avoid same fire
        try:
            from datetime import timedelta
            current = nxt + timedelta(seconds=1)
        except Exception:
            break
    return runs


def human_cron(cron_expr: str) -> str:
    """Lightweight human preview using 24-hour time format (HH:MM)."""
    expr = cron_expr.strip()
    if not expr:
        return ""

    parts = expr.split()
    if len(parts) != 5:
        return expr

    minute, hour, dom, month, dow = parts
    dow_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    month_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    # Special well-known phrases
    if expr == "* * * * *":
        return "Every minute"
    if minute.startswith("*/") and minute[2:].isdigit() and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every {minute[2:]} minutes"
    if minute == "0" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return "Every hour, at minute 0"
    if minute == "0" and hour.startswith("*/") and hour[2:].isdigit() and dom == "*" and month == "*" and dow == "*":
        return f"Every {hour[2:]} hours, at minute 0"

    # Specific minute and hour (e.g. "0 0 * * *", "40 11 * * *", "0 18 * * 0")
    if minute.isdigit() and hour.isdigit():
        m = int(minute)
        h = int(hour)
        if 0 <= m <= 59 and 0 <= h <= 23:
            time_str = f"{h:02d}:{m:02d}"

            # Daily: "0 0 * * *", "40 11 * * *"
            if dom == "*" and month == "*" and dow == "*":
                return f"At {time_str}, every day"

            # Weekdays: "0 18 * * 1-5"
            if dom == "*" and month == "*" and dow in ("1-5", "1,2,3,4,5"):
                return f"At {time_str}, Monday through Friday"

            # Weekends: "0 18 * * 0,6"
            if dom == "*" and month == "*" and dow in ("0,6", "6,0", "0,7", "7,6", "6,7"):
                return f"At {time_str}, only on weekends"

            # Specific day(s) of week: "0 18 * * 0", "0 18 * * 1,4"
            if dom == "*" and month == "*":
                dow_items = dow.split(",")
                valid_dows = []
                for d in dow_items:
                    if d.isdigit() and 0 <= int(d) <= 7:
                        val = int(d)
                        if val == 7:
                            val = 0
                        valid_dows.append(dow_names[val])
                    else:
                        valid_dows = []
                        break
                if valid_dows:
                    if len(valid_dows) == 1:
                        return f"At {time_str}, only on {valid_dows[0]}"
                    elif len(valid_dows) == 2:
                        return f"At {time_str}, only on {valid_dows[0]} and {valid_dows[1]}"
                    else:
                        return f"At {time_str}, only on {', '.join(valid_dows[:-1])}, and {valid_dows[-1]}"

            # Day of month: "0 18 1 * *"
            if dom.isdigit() and month == "*" and dow == "*":
                return f"At {time_str}, on day {dom} of every month"

            # Specific month & day: "0 18 1 1 *"
            if dom.isdigit() and month.isdigit() and dow == "*":
                mn = int(month)
                if 1 <= mn <= 12:
                    return f"At {time_str}, on {month_names[mn]} {dom}"

    # Fallback to cron_descriptor if installed with 24-hour option
    try:
        from cron_descriptor import Options, get_description  # type: ignore
        opt = Options()
        opt.use_24hour_time_format = True
        return get_description(cron_expr, opt)
    except Exception:
        pass

    return expr


def fire_schedule(schedule_id: str) -> None:
    """Job function: insert pending_commands for the schedule."""
    # Lazy imports to avoid circular
    from databasev5 import SessionLocal
    from modelsv5 import schedules, pending_commands

    db = SessionLocal()
    try:
        s = db.get(schedules, schedule_id)
        if not s or not s.enabled:
            logger.info(f"fire_schedule skip: schedule {schedule_id} not found or disabled")
            return
        # Insert pending_commands — firmware bundling contract: payload already bundled e.g. {mode:manual,start_genset:on}
        cmd = pending_commands(
            command_id=str(uuid.uuid4()),
            dev_id=s.dev_id,
            hub_id=s.hub_id or _resolve_hub_for_device(db, s.dev_id) or s.hub_id,
            payload=s.payload,
            status="pending",
        )
        # Guard: if hub_id still None, fail gracefully
        if not cmd.hub_id:
            logger.warning(f"fire_schedule {schedule_id}: no hub_id resolved for dev {s.dev_id}, skipping")
            return
        db.add(cmd)
        # Update next_run_at
        try:
            nxt = get_next_runs(s.cron_expr, s.tz, 1)
            if nxt:
                s.next_run_at = nxt[0]
        except Exception:
            pass
        db.commit()
        logger.info(f"fire_schedule {schedule_id} -> pending_commands {cmd.command_id} dev={s.dev_id}")
    except Exception as e:
        logger.exception(f"fire_schedule {schedule_id} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _resolve_hub_for_device(db, dev_id: str) -> Optional[str]:
    try:
        from modelsv5 import dev_table
        dev = db.get(dev_table, dev_id)
        if dev and dev.hub_id:
            return dev.hub_id
    except Exception:
        pass
    return None


def _load_enabled_schedules():
    from databasev5 import SessionLocal
    from modelsv5 import schedules
    db = SessionLocal()
    try:
        return db.query(schedules).filter(schedules.enabled == True).all()  # noqa: E712
    finally:
        db.close()


def _build_scheduler() -> BackgroundScheduler:
    """Build scheduler with optional SQLAlchemyJobStore if DATABASE_URL is postgres."""
    from databasev5 import DATABASE_URL

    jobstores = {}
    # Try SQLAlchemyJobStore for postgres persistence; fallback to memory for sqlite/tests
    if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres"):
        try:
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
            logger.info("Scheduler using SQLAlchemyJobStore")
        except Exception as e:
            logger.warning(f"SQLAlchemyJobStore init failed, using memory: {e}")
            jobstores = {}
    # else: default in-memory store (sufficient for <1k jobs, rehydrated on restart)
    sched = BackgroundScheduler(jobstores=jobstores, job_defaults=JOB_DEFAULTS, timezone=CANONICAL_TZ)
    return sched


def sync_job(schedule_id: str, cron_expr: str, tz: str, enabled: bool) -> None:
    """Sync single schedule to APScheduler. Call after CRUD."""
    global scheduler
    if scheduler is None or not scheduler.running:
        return
    job_id = f"schedule-{schedule_id}"
    existing = scheduler.get_job(job_id)
    if not enabled:
        if existing:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        return
    trigger = CronTrigger.from_crontab(cron_expr.strip(), timezone=tz)
    if existing:
        try:
            scheduler.reschedule_job(job_id, trigger=trigger)
            # Update args in case schedule_id changed? no
        except Exception:
            # fallback remove+add
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
            scheduler.add_job(
                fire_schedule,
                trigger=trigger,
                args=[schedule_id],
                id=job_id,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=60,
            )
    else:
        scheduler.add_job(
            fire_schedule,
            trigger=trigger,
            args=[schedule_id],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )


def remove_job(schedule_id: str) -> None:
    global scheduler
    if scheduler is None or not scheduler.running:
        return
    job_id = f"schedule-{schedule_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def checkpoint_sqlite_wal() -> None:
    """Hourly maintenance job to truncate SQLite WAL and reclaim disk space."""
    try:
        from databasev5 import engine, IS_SQLITE
        from sqlalchemy import text
        if IS_SQLITE:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
                conn.commit()
            logger.info("SQLite WAL checkpoint (TRUNCATE) executed successfully")
    except Exception as e:
        logger.warning(f"SQLite WAL checkpoint failed: {e}")


@asynccontextmanager
async def scheduler_lifespan(app):
    """FastAPI lifespan that starts/stops APScheduler and rehydrates jobs."""
    # Ensure database composite and unique indexes exist (especially for SQLite/PG UPSERT)
    try:
        from databasev5 import engine, migrate_indexes
        migrate_indexes(engine)
    except Exception as e:
        logger.warning(f"Startup migrate_indexes failed/skipped: {e}")

    global scheduler
    scheduler = _build_scheduler()

    # Rehydrate schedules using a single scoped SessionLocal()
    from databasev5 import SessionLocal
    from modelsv5 import schedules
    from sqlalchemy import select
    from app.services.presence import evaluate_device_presence_batch, PRESENCE_INTERVAL_SECONDS

    db = SessionLocal()
    try:
        enabled_schedules = (
            db.execute(select(schedules).where(schedules.enabled == True))  # noqa: E712
            .scalars()
            .all()
        )

        has_updates = False
        for s in enabled_schedules:
            try:
                tz_str = s.tz or CANONICAL_TZ
                _validate_cron_expr(s.cron_expr, tz_str)
                trigger = CronTrigger.from_crontab(s.cron_expr.strip(), timezone=tz_str)
                scheduler.add_job(
                    fire_schedule,
                    trigger=trigger,
                    args=[s.id],
                    id=f"schedule-{s.id}",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=60,
                )
                try:
                    nxt = get_next_runs(s.cron_expr, tz_str, 1)
                    if nxt and s.next_run_at != nxt[0]:
                        s.next_run_at = nxt[0]
                        has_updates = True
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Failed to rehydrate schedule {s.id}: {e}")

        if has_updates:
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to load schedules during startup: {e}")
    finally:
        db.close()

    # Register background presence evaluation job
    scheduler.add_job(
        evaluate_device_presence_batch,
        trigger="interval",
        seconds=PRESENCE_INTERVAL_SECONDS,
        id="engine-device-presence",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=15,
    )

    # Register hourly SQLite WAL checkpoint job
    scheduler.add_job(
        checkpoint_sqlite_wal,
        trigger="interval",
        hours=1,
        id="engine-sqlite-wal-checkpoint",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    try:
        scheduler.start()
        logger.info("APScheduler started")
    except Exception as e:
        logger.warning(f"Scheduler start failed (may already running): {e}")

    try:
        yield
    finally:
        if scheduler:
            try:
                scheduler.shutdown(wait=False)
                logger.info("APScheduler shutdown")
            except Exception:
                pass
            scheduler = None
