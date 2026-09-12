# app/services/partition_manager.py — Automated partition lifecycle management for PostgreSQL 16
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from databasev5 import engine, IS_SQLITE

logger = logging.getLogger("partition_manager")

TELEMETRY_TABLES = ["data_table", "temperature_data", "ats_data"]
RETENTION_DAYS = 30


def _add_months(dt: datetime, months: int) -> datetime:
    """Calculate date shifted by N months with 1st of month at 00:00:00 UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    total_months = dt.year * 12 + (dt.month - 1) + months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1
    return dt.replace(
        year=new_year,
        month=new_month,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _generate_partition_ddl(table: str, target_month_start: datetime, target_month_end: datetime) -> tuple[str, str]:
    """Generate child partition name and DDL for a given month range."""
    part_name = f"{table}_y{target_month_start.strftime('%Y_%m')}"
    from_val = target_month_start.isoformat()
    to_val = target_month_end.isoformat()
    ddl = (
        f'CREATE TABLE IF NOT EXISTS "{part_name}" PARTITION OF "{table}" '
        f"FOR VALUES FROM ('{from_val}') TO ('{to_val}');"
    )
    return part_name, ddl


def _parse_partition_upper_bound(bound_expr: Optional[str]) -> Optional[datetime]:
    """Extract upper bound timestamp from PostgreSQL relpartbound expression.
    Example: FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00')"""
    if not bound_expr or "TO ('" not in bound_expr:
        return None
    try:
        to_str = bound_expr.split("TO ('")[1].split("')")[0]
        dt = datetime.fromisoformat(to_str)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except Exception as ex:
        logger.debug(f"Failed to parse partition upper bound from '{bound_expr}': {ex}")
        return None


def _precreate_future_partitions(conn, table: str, now: datetime) -> list[str]:
    """Ensure child partitions exist for current month (T), next month (T+1), and month after next (T+2)."""
    created = []
    for offset_months in [0, 1, 2]:
        target_month_start = _add_months(now, offset_months)
        target_month_end = _add_months(now, offset_months + 1)
        part_name, ddl = _generate_partition_ddl(table, target_month_start, target_month_end)

        try:
            conn.execute(text(ddl))
            logger.debug(f"Ensured partition exists: {part_name}")
            created.append(part_name)
        except Exception as ex:
            logger.error(f"Failed to pre-create partition {part_name}: {ex}")

    return created


def _prune_expired_partitions(conn, table: str, now: datetime) -> list[str]:
    """Detach CONCURRENTLY and drop partitions containing data strictly older than retention threshold."""
    retention_cutoff = now - timedelta(days=RETENTION_DAYS)
    pruned = []

    # Query PostgreSQL system catalog for child partitions
    query = text("""
        SELECT
            c.relname AS child_name,
            pg_get_expr(c.relpartbound, c.oid) AS bound_expr
        FROM pg_class c
        JOIN pg_inherits i ON i.inhrelid = c.oid
        JOIN pg_class p ON p.oid = i.inhparent
        WHERE p.relname = :parent_table
        ORDER BY c.relname ASC;
    """)

    try:
        rows = conn.execute(query, {"parent_table": table}).fetchall()
    except Exception as ex:
        logger.error(f"Failed to query child partitions for {table}: {ex}")
        return pruned

    for row in rows:
        child_name = row.child_name
        bound_expr = row.bound_expr

        upper_bound = _parse_partition_upper_bound(bound_expr)
        if upper_bound is None:
            continue

        if upper_bound < retention_cutoff:
            logger.warning(
                f"Partition {child_name} is older than {RETENTION_DAYS}d retention "
                f"(upper bound: {upper_bound.isoformat()}). Detaching CONCURRENTLY..."
            )
            try:
                # Phase 1: Detach partition non-blockingly (requires autocommit)
                conn.execute(text(f'ALTER TABLE "{table}" DETACH PARTITION "{child_name}" CONCURRENTLY;'))
                logger.info(f"Successfully detached expired partition {child_name}.")

                # Phase 2: Drop detached standalone table
                conn.execute(text(f'DROP TABLE IF EXISTS "{child_name}";'))
                logger.info(f"Dropped expired standalone table {child_name}.")
                pruned.append(child_name)
            except Exception as ex:
                logger.error(f"Error during pruning execution for {child_name}: {ex}")

    return pruned


def run_partition_maintenance(target_engine=None, now_utc: Optional[datetime] = None) -> None:
    """Automated daily lifecycle worker:
    1. Bypasses cleanly on SQLite dialect.
    2. Pre-creates future partitions for T, T+1, and T+2 months.
    3. Non-blockingly detaches partitions older than 30 days via DETACH CONCURRENTLY.
    4. Drops detached standalone child tables to reclaim disk space instantly.
    """
    active_engine = target_engine or engine
    if IS_SQLITE and target_engine is None:
        logger.debug("Partition maintenance skipped on SQLite dialect.")
        return
    if hasattr(active_engine, "dialect") and active_engine.dialect.name == "sqlite":
        logger.debug("Partition maintenance skipped on SQLite dialect.")
        return

    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    logger.info("Starting automated PostgreSQL 16 partition lifecycle maintenance...")

    # Autocommit connection required: DETACH CONCURRENTLY cannot run inside a transaction
    with active_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("SET lock_timeout = '3s';"))
        conn.execute(text("SET statement_timeout = '30s';"))

        for table in TELEMETRY_TABLES:
            _precreate_future_partitions(conn, table, now)
            _prune_expired_partitions(conn, table, now)

    logger.info("Partition lifecycle maintenance completed successfully.")
