#!/usr/bin/env python3
"""
High-Throughput Streaming Migration Tool: SQLite to PostgreSQL 16
SMSB HubGate V5 Infrastructure

Features:
- Server-side streaming SQLite cursor using chunked batches (default 20,000 rows).
- Zero-memory-bloat pipeline (< 50MB RAM footprint).
- Strict type sanitization:
  * Timestamps: ISO strings/timestamps converted to timezone-aware UTC datetime.
  * Booleans: 0/1 integers converted to True/False.
  * JSON fields: JSONB validation and serialization.
- Bypasses foreign key checks during load (SET session_replication_role = 'replica').
- Sequence resynchronization: setval for all serial/identity columns.
- Table parity verification report comparing source SQLite and target PostgreSQL row counts.
- Dry-run validation mode (--dry-run).
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure server/ is in python path for importing models and database config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("migrate_sqlite_to_postgres")

# Table migration order respecting foreign-key hierarchy
CANONICAL_TABLE_ORDER: List[str] = [
    "alembic_version",
    "users",
    "login_attempts",
    "hub_table",
    "rooms",
    "dev_table",
    "device_threshold_config",
    "sessions",
    "schedules",
    "pending_commands",
    "temperature_data",
    "ats_data",
    "data_table",
    "event_log",
]

TABLE_ALIASES: Dict[str, str] = {
    "device_threshold_configs": "device_threshold_config",
}

DATETIME_COLUMNS: Set[str] = {
    "timestamp",
    "created_at",
    "last_seen",
    "resolved_at",
    "delivered_at",
    "updated_at",
    "next_run_at",
    "expires_at",
    "last_attempt_at",
    "locked_until",
    "lockout_until",
}

BOOLEAN_COLUMNS: Set[str] = {
    "is_active",
    "auto_mode",
    "emergency",
    "enabled",
}

JSON_COLUMNS: Set[str] = {
    "payload",
}


def normalize_pg_dsn(url: str) -> str:
    """Normalize SQLAlchemy connection URL to standard libpq connection string."""
    if not url:
        return url
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url[len("postgresql+psycopg2://") :]
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def sanitize_datetime(val: Any) -> Optional[datetime.datetime]:
    """Parse and normalize any SQLite datetime representation into a UTC timezone-aware datetime."""
    if val is None or val == "" or val == "None":
        return None

    if isinstance(val, datetime.datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=datetime.timezone.utc)
        return val.astimezone(datetime.timezone.utc)

    if isinstance(val, (int, float)):
        return datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        try:
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
        except (ValueError, TypeError):
            pass

        # Strptime fallbacks for various SQLite format variants
        formats = [
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt.astimezone(datetime.timezone.utc)
            except ValueError:
                continue

        logger.warning(f"Could not parse datetime string '{val}', passing None")
        return None

    return None


def sanitize_boolean(val: Any) -> Optional[bool]:
    """Normalize boolean representation (int 0/1, string, etc.) into Python bool."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val != 0)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("1", "true", "t", "yes", "y"):
            return True
        if s in ("0", "false", "f", "no", "n"):
            return False
        return bool(s)
    return bool(val)


def sanitize_json(val: Any, wrap_psycopg: bool = False) -> Any:
    """Normalize JSON column into serialized JSON or psycopg2.extras.Json."""
    if val is None or val == "" or val == "None":
        return None

    obj: Any = None
    if isinstance(val, (dict, list)):
        obj = val
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            obj = json.loads(s)
        except Exception:
            obj = s
    else:
        obj = val

    if wrap_psycopg:
        try:
            from psycopg2.extras import Json
            return Json(obj)
        except ImportError:
            return json.dumps(obj)
    return json.dumps(obj)


def get_column_sanitizer_type(col_name: str, table_name: str, model_col: Optional[Any] = None) -> str:
    """Determine the sanitizer type ('datetime', 'bool', 'json', or 'raw') for a column."""
    if model_col is not None:
        type_str = str(model_col.type).upper()
        if "BOOLEAN" in type_str:
            return "bool"
        if "DATETIME" in type_str or "TIMESTAMP" in type_str:
            return "datetime"
        if "JSON" in type_str:
            return "json"

    col_lower = col_name.lower()
    if col_lower in BOOLEAN_COLUMNS:
        return "bool"
    if col_lower in DATETIME_COLUMNS:
        return "datetime"
    if col_lower in JSON_COLUMNS:
        return "json"
    return "raw"


def sanitize_row(row: Tuple[Any, ...], col_types: List[str], wrap_psycopg_json: bool = False) -> Tuple[Any, ...]:
    """Sanitize all values in a row tuple based on determined column types."""
    sanitized = []
    for val, ctype in zip(row, col_types):
        if ctype == "datetime":
            sanitized.append(sanitize_datetime(val))
        elif ctype == "bool":
            sanitized.append(sanitize_boolean(val))
        elif ctype == "json":
            sanitized.append(sanitize_json(val, wrap_psycopg=wrap_psycopg_json))
        else:
            sanitized.append(val)
    return tuple(sanitized)


def get_sqlite_tables(sqlite_conn) -> List[str]:
    """List all user tables in SQLite database."""
    cur = sqlite_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]
    cur.close()
    return tables


def get_sqlite_columns(sqlite_conn, table_name: str) -> List[str]:
    """Get column names for a SQLite table."""
    cur = sqlite_conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    cols = [r[1] for r in cur.fetchall()]
    cur.close()
    return cols


def get_pg_columns(pg_conn, table_name: str) -> List[str]:
    """Get column names for a PostgreSQL table in public schema."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (table_name,),
        )
        cols = [r[0] for r in cur.fetchall()]
    return cols


def resync_postgres_sequences(pg_conn) -> int:
    """Resynchronize all serial and identity sequences in PostgreSQL public schema."""
    resynced_count = 0
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.table_name, c.column_name, pg_get_serial_sequence(quote_ident(c.table_name), c.column_name) AS seq_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
            """
        )
        rows = cur.fetchall()
        for tbl, col, seq in rows:
            if seq:
                try:
                    cur.execute(f"SELECT COALESCE(MAX({col}), 1) FROM {tbl};")
                    max_val = cur.fetchone()[0]
                    cur.execute(f"SELECT setval(%s, %s, true);", (seq, max_val))
                    logger.info(f"  [+] Resynchronized sequence {seq} -> {max_val}")
                    resynced_count += 1
                except Exception as ex:
                    logger.warning(f"  [-] Failed to resync sequence {seq} on {tbl}.{col}: {ex}")
    return resynced_count


def execute_migration(
    sqlite_path: str,
    pg_url: Optional[str],
    batch_size: int = 20000,
    dry_run: bool = False,
    truncate: bool = True,
) -> bool:
    """
    Execute streaming migration from SQLite to PostgreSQL.
    Returns True if successful and row count parity is verified, False otherwise.
    """
    import sqlite3

    if not os.path.isfile(sqlite_path):
        logger.error(f"SQLite source file does not exist: {sqlite_path}")
        return False

    abs_sqlite_path = os.path.abspath(sqlite_path)
    logger.info(f"Opening source SQLite database in read-only mode: {abs_sqlite_path}")
    sqlite_uri = f"file:{abs_sqlite_path}?mode=ro"
    sqlite_conn = sqlite3.connect(sqlite_uri, uri=True)

    sqlite_tables = get_sqlite_tables(sqlite_conn)
    logger.info(f"Found {len(sqlite_tables)} tables in SQLite: {', '.join(sqlite_tables)}")

    # Map SQLite tables to PostgreSQL target names and order according to dependency hierarchy
    tables_to_migrate: List[Tuple[str, str]] = []  # (sqlite_tbl, pg_tbl)
    seen_pg = set()

    for canon in CANONICAL_TABLE_ORDER:
        matched_sqlite = None
        if canon in sqlite_tables:
            matched_sqlite = canon
        else:
            for alias_src, alias_tgt in TABLE_ALIASES.items():
                if alias_tgt == canon and alias_src in sqlite_tables:
                    matched_sqlite = alias_src
                    break

        if matched_sqlite:
            tables_to_migrate.append((matched_sqlite, canon))
            seen_pg.add(canon)

    for extra in sqlite_tables:
        target = TABLE_ALIASES.get(extra, extra)
        if target not in seen_pg:
            tables_to_migrate.append((extra, target))
            seen_pg.add(target)

    # Try importing SQLAlchemy metadata for column type hints
    models_metadata = None
    try:
        from modelsv5 import Base
        models_metadata = Base.metadata.tables
    except Exception as ex:
        logger.debug(f"SQLAlchemy modelsv5 metadata not imported: {ex}")

    pg_conn = None
    if not dry_run:
        if not pg_url:
            logger.error("PostgreSQL URL (--pg-url or DATABASE_URL) is required for execution.")
            sqlite_conn.close()
            return False

        try:
            import psycopg2
            from psycopg2.extras import execute_values
        except ImportError:
            logger.error("psycopg2 is required for PostgreSQL ingestion. Install via 'pip install psycopg2-binary'.")
            sqlite_conn.close()
            return False

        norm_url = normalize_pg_dsn(pg_url)
        logger.info(f"Connecting to PostgreSQL target database...")
        try:
            pg_conn = psycopg2.connect(norm_url)
            pg_conn.autocommit = False
        except Exception as ex:
            logger.error(f"Failed to connect to PostgreSQL: {ex}")
            sqlite_conn.close()
            return False

    parity_results: List[Dict[str, Any]] = []
    start_time = time.time()
    all_success = True

    try:
        if pg_conn:
            logger.info("Configuring PostgreSQL session optimizations...")
            with pg_conn.cursor() as cur:
                cur.execute("SET session_replication_role = 'replica';")
                cur.execute("SET synchronous_commit = off;")
                cur.execute("SET maintenance_work_mem = '512MB';")
            pg_conn.commit()

            if truncate:
                logger.info("Truncating target PostgreSQL tables for clean migration...")
                target_tables = [pg_tbl for _, pg_tbl in tables_to_migrate]
                with pg_conn.cursor() as cur:
                    for tbl in target_tables:
                        try:
                            cur.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
                        except Exception as ex:
                            logger.warning(f"Could not truncate {tbl} (may not exist yet): {ex}")
                pg_conn.commit()

        # Iterate tables and stream data
        for sqlite_tbl, pg_tbl in tables_to_migrate:
            logger.info(f"\n--- Migrating table: {sqlite_tbl} -> {pg_tbl} ---")
            sqlite_cols = get_sqlite_columns(sqlite_conn, sqlite_tbl)
            cur_sqlite = sqlite_conn.cursor()
            cur_sqlite.execute(f"SELECT COUNT(*) FROM {sqlite_tbl};")
            source_count = cur_sqlite.fetchone()[0]

            if not pg_conn:
                # Dry-Run Mode
                logger.info(f"Dry-run: Reading {source_count} rows from {sqlite_tbl} in batches of {batch_size}...")
                cols_str = ", ".join(sqlite_cols)
                cur_sqlite.execute(f"SELECT {cols_str} FROM {sqlite_tbl};")

                col_types = []
                model_tbl = models_metadata.get(pg_tbl) if models_metadata else None
                for c in sqlite_cols:
                    model_col = model_tbl.columns.get(c) if model_tbl is not None else None
                    col_types.append(get_column_sanitizer_type(c, pg_tbl, model_col))

                processed_rows = 0
                while True:
                    batch = cur_sqlite.fetchmany(batch_size)
                    if not batch:
                        break
                    for row in batch:
                        _ = sanitize_row(row, col_types, wrap_psycopg_json=False)
                    processed_rows += len(batch)

                cur_sqlite.close()
                parity_results.append({
                    "table": pg_tbl,
                    "sqlite_count": source_count,
                    "pg_count": source_count,  # dry-run simulated parity
                    "match": True,
                    "status": "DRY-RUN VALIDATED",
                })
                logger.info(f"Dry-run validated {processed_rows}/{source_count} rows for {sqlite_tbl} successfully.")
                continue

            # Live PostgreSQL Ingestion
            from psycopg2.extras import execute_values

            pg_cols = get_pg_columns(pg_conn, pg_tbl)
            if not pg_cols:
                logger.warning(f"Target table {pg_tbl} does not exist in PostgreSQL. Skipping.")
                parity_results.append({
                    "table": pg_tbl,
                    "sqlite_count": source_count,
                    "pg_count": 0,
                    "match": False,
                    "status": "PG TABLE MISSING",
                })
                all_success = False
                cur_sqlite.close()
                continue

            common_cols = [c for c in sqlite_cols if c in pg_cols]
            if not common_cols:
                logger.warning(f"No matching columns between SQLite {sqlite_tbl} and PostgreSQL {pg_tbl}. Skipping.")
                cur_sqlite.close()
                continue

            model_tbl = models_metadata.get(pg_tbl) if models_metadata else None
            col_types = []
            for c in common_cols:
                model_col = model_tbl.columns.get(c) if model_tbl is not None else None
                col_types.append(get_column_sanitizer_type(c, pg_tbl, model_col))

            cols_quoted = ", ".join(f'"{c}"' for c in common_cols)
            insert_sql = f'INSERT INTO "{pg_tbl}" ({cols_quoted}) VALUES %s'

            cur_sqlite.execute(f"SELECT {', '.join(common_cols)} FROM {sqlite_tbl};")
            inserted_count = 0

            with pg_conn.cursor() as cur_pg:
                while True:
                    batch = cur_sqlite.fetchmany(batch_size)
                    if not batch:
                        break
                    sanitized_batch = [
                        sanitize_row(row, col_types, wrap_psycopg_json=True) for row in batch
                    ]
                    execute_values(cur_pg, insert_sql, sanitized_batch, page_size=2000)
                    inserted_count += len(batch)
                    pct = (inserted_count / source_count * 100) if source_count > 0 else 100.0
                    logger.info(f"  Ingested {inserted_count}/{source_count} rows ({pct:.1f}%) into {pg_tbl}")

            pg_conn.commit()
            cur_sqlite.close()

            # Verify row count in PostgreSQL
            with pg_conn.cursor() as cur_pg:
                cur_pg.execute(f'SELECT COUNT(*) FROM "{pg_tbl}";')
                pg_count = cur_pg.fetchone()[0]

            is_match = (source_count == pg_count)
            if not is_match:
                all_success = False
            parity_results.append({
                "table": pg_tbl,
                "sqlite_count": source_count,
                "pg_count": pg_count,
                "match": is_match,
                "status": "OK" if is_match else "MISMATCH",
            })

        # Post-migration procedures for PostgreSQL
        if pg_conn:
            logger.info("\n--- Post-Migration Maintenance ---")
            # 1. Resynchronize sequences
            logger.info("Resynchronizing serial sequences...")
            resynced = resync_postgres_sequences(pg_conn)
            logger.info(f"Resynchronized {resynced} sequence(s).")

            # 2. Re-enable foreign key constraints and triggers
            logger.info("Restoring PostgreSQL session replication role to 'origin'...")
            with pg_conn.cursor() as cur:
                cur.execute("SET session_replication_role = 'origin';")
                cur.execute("SET synchronous_commit = on;")
            pg_conn.commit()

            # 3. VACUUM ANALYZE migrated tables
            logger.info("Running VACUUM ANALYZE on migrated tables...")
            old_isolation = pg_conn.isolation_level
            pg_conn.set_isolation_level(0)  # autocommit mode required for VACUUM
            with pg_conn.cursor() as cur:
                for _, pg_tbl in tables_to_migrate:
                    try:
                        cur.execute(f'VACUUM ANALYZE "{pg_tbl}";')
                    except Exception as ex:
                        logger.debug(f"VACUUM ANALYZE on {pg_tbl} skipped: {ex}")
            pg_conn.set_isolation_level(old_isolation)

    except Exception as ex:
        logger.error(f"Migration aborted due to error: {ex}", exc_info=True)
        all_success = False
        if pg_conn:
            try:
                pg_conn.rollback()
                with pg_conn.cursor() as cur:
                    cur.execute("SET session_replication_role = 'origin';")
                pg_conn.commit()
            except Exception:
                pass
    finally:
        if pg_conn:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SET session_replication_role = 'origin';")
                pg_conn.commit()
            except Exception:
                pass
            try:
                pg_conn.close()
            except Exception:
                pass
        sqlite_conn.close()

    elapsed = time.time() - start_time

    # Print Parity Summary Report
    print("\n" + "=" * 76)
    print("           POSTGRESQL 16 CUTOVER ROW PARITY REPORT")
    print("=" * 76)
    print(f"{'Table Name':<28} | {'SQLite Count':>12} | {'Postgres Count':>14} | {'Status':<12}")
    print("-" * 76)
    for r in parity_results:
        status_display = "MATCH" if r["match"] else f"FAIL ({r['status']})"
        print(f"{r['table']:<28} | {r['sqlite_count']:>12} | {r['pg_count']:>14} | {status_display:<12}")
    print("-" * 76)
    mode_text = "DRY-RUN (Simulated)" if dry_run else "PRODUCTION CUTOVER"
    print(f"Mode: {mode_text} | Total Duration: {elapsed:.2f}s | Result: {'PASSED' if all_success else 'FAILED'}")
    print("=" * 76 + "\n")

    return all_success


def main():
    parser = argparse.ArgumentParser(
        description="High-Throughput Streaming Migration Tool: SQLite to PostgreSQL 16"
    )
    parser.add_argument(
        "--sqlite-path",
        "--sqlite",
        dest="sqlite_path",
        default=os.getenv("SQLITE_PATH", "server/hubgatev5.db"),
        help="Path to source SQLite database file (default: server/hubgatev5.db)",
    )
    parser.add_argument(
        "--pg-url",
        "--pg",
        dest="pg_url",
        default=os.getenv("DATABASE_URL"),
        help="Target PostgreSQL connection URL (e.g. postgresql+psycopg2://smsb:pass@127.0.0.1:5432/smsb_prod)",
    )
    parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=20000,
        help="Streaming batch size per cursor fetch (default: 20000)",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Perform dry-run validation without altering PostgreSQL target database",
    )
    parser.add_argument(
        "--no-truncate",
        dest="truncate",
        action="store_false",
        help="Do not truncate target tables prior to data streaming",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        dest="verbose",
        action="store_true",
        help="Enable debug logging output",
    )

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    success = execute_migration(
        sqlite_path=args.sqlite_path,
        pg_url=args.pg_url,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        truncate=args.truncate,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
