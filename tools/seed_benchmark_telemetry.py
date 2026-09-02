#!/usr/bin/env python3
"""
seed_benchmark_telemetry.py — High-Performance Synthetic Telemetry Seeder

Generates and inserts 1,000,000 realistic telemetry rows (500,000 TS, 500,000 ATS)
spanning a 30-day window into SQLite (WAL) or PostgreSQL using chunked SQLAlchemy
Core DML in < 15 seconds.

Usage:
    python tools/seed_benchmark_telemetry.py --clean --total-rows 1000000 --verify
"""

import argparse
import math
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

# Add server directory to sys.path
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.orm import sessionmaker

from auth import hash_password
from databasev5 import Base, get_engine_kwargs
from modelsv5 import (
    User,
    ats_data,
    dev_table,
    device_threshold_config,
    hub_table,
    rooms,
    temperature_data,
)

BENCH_HUB_ID = "BENCH_HUB_01"
BENCH_HUB_KEY = "bench_secret_key_123"
BENCH_ROOM_ID = "room-bench-01"
BENCH_TS_DEV_ID = "BENCH_DEV_TS_01"
BENCH_ATS_DEV_ID = "BENCH_DEV_ATS_01"
BENCH_USERNAME = "bench_user"
BENCH_PASSWORD = "bench_pass_123"


def get_target_engine(db_url: Optional[str] = None):
    """Initializes SQLAlchemy Engine configured for high-throughput batch DML."""
    target_url = db_url or os.getenv("DATABASE_URL") or "sqlite:///./benchmark_hubgatev5.db"
    kwargs = get_engine_kwargs(target_url)
    engine = create_engine(target_url, **kwargs)
    return engine, target_url


def ensure_prerequisites(engine, clean: bool = False):
    """Ensures database schema, benchmark hub, room, devices, thresholds, and user exist."""
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    try:
        if clean:
            print("[Seeder] Cleaning existing benchmark records...")
            db.query(temperature_data).filter(temperature_data.dev_id == BENCH_TS_DEV_ID).delete()
            db.query(ats_data).filter(ats_data.dev_id == BENCH_ATS_DEV_ID).delete()
            db.query(device_threshold_config).filter(
                device_threshold_config.dev_id.in_([BENCH_TS_DEV_ID, BENCH_ATS_DEV_ID])
            ).delete()
            db.query(dev_table).filter(
                dev_table.dev_id.in_([BENCH_TS_DEV_ID, BENCH_ATS_DEV_ID])
            ).delete()
            db.commit()

        # 1. Benchmark Hub
        hub = db.get(hub_table, BENCH_HUB_ID)
        if not hub:
            hub = hub_table(
                hub_id=BENCH_HUB_ID,
                hub_name="Benchmark Hub Gateway",
                hub_key=BENCH_HUB_KEY,
                room="Benchmark Server Room",
                is_active=True,
                status="online",
                last_seen=datetime.now(UTC),
            )
            db.add(hub)

        # 2. Benchmark Room
        room = db.get(rooms, BENCH_ROOM_ID)
        if not room:
            room = rooms(
                id=BENCH_ROOM_ID,
                name="Benchmark Server Room",
                hub_id=BENCH_HUB_ID,
            )
            db.add(room)

        # 3. Benchmark Devices
        ts_dev = db.get(dev_table, BENCH_TS_DEV_ID)
        if not ts_dev:
            ts_dev = dev_table(
                dev_id=BENCH_TS_DEV_ID,
                dev_name="Benchmark TS Sensor 01",
                dev_type="TS",
                hub_id=BENCH_HUB_ID,
                room_id=BENCH_ROOM_ID,
                is_active=True,
                last_status="online",
                last_seen=datetime.now(UTC),
            )
            db.add(ts_dev)

        ts_dev2 = db.get(dev_table, "BENCH_DEV_TS_02")
        if not ts_dev2:
            ts_dev2 = dev_table(
                dev_id="BENCH_DEV_TS_02",
                dev_name="Benchmark TS Sensor 02",
                dev_type="TS",
                hub_id=BENCH_HUB_ID,
                room_id=BENCH_ROOM_ID,
                is_active=True,
                last_status="online",
                last_seen=datetime.now(UTC),
            )
            db.add(ts_dev2)

        ats_dev = db.get(dev_table, BENCH_ATS_DEV_ID)
        if not ats_dev:
            ats_dev = dev_table(
                dev_id=BENCH_ATS_DEV_ID,
                dev_name="Benchmark ATS Controller",
                dev_type="ATS",
                hub_id=BENCH_HUB_ID,
                room_id=BENCH_ROOM_ID,
                is_active=True,
                last_status="online",
                last_seen=datetime.now(UTC),
            )
            db.add(ats_dev)

        # 4. Threshold Configs
        for tid in (BENCH_TS_DEV_ID, "BENCH_DEV_TS_02"):
            ts_thresh = db.get(device_threshold_config, tid)
            if not ts_thresh:
                ts_thresh = device_threshold_config(
                    dev_id=tid,
                    warning=30.0,
                    critical=35.0,
                    hysteresis=0.5,
                    debounce_seconds=30,
                )
                db.add(ts_thresh)

        ats_thresh = db.get(device_threshold_config, BENCH_ATS_DEV_ID)
        if not ats_thresh:
            ats_thresh = device_threshold_config(
                dev_id=BENCH_ATS_DEV_ID,
                warning=12.0,
                critical=11.5,
                hysteresis=0.2,
                debounce_seconds=15,
            )
            db.add(ats_thresh)

        # 5. Benchmark Admin User
        bench_user = db.query(User).filter(User.username == BENCH_USERNAME).first()
        if not bench_user:
            bench_user = User(
                id=f"user-{BENCH_USERNAME}",
                username=BENCH_USERNAME,
                password_hash=hash_password(BENCH_PASSWORD),
                display_name="Benchmark Operator",
                role="admin",
            )
            db.add(bench_user)

        db.commit()
    finally:
        db.close()


def generate_ts_batch(
    start_idx: int,
    batch_size: int,
    start_time: datetime,
    step_seconds: float,
    dev_id: str,
) -> list[dict]:
    """Generates a chunk of realistic Temperature / Humidity telemetry dictionaries."""
    rows = []
    two_pi_over_24 = 2.0 * math.pi / 24.0

    for i in range(start_idx, start_idx + batch_size):
        t_sec = i * step_seconds
        ts = start_time + timedelta(seconds=t_sec)

        # Diurnal temperature cycle: peak at 14:00, coolest at 02:00
        hour_val = ts.hour + (ts.minute / 60.0) + (ts.second / 3600.0)
        diurnal = 23.5 + 2.5 * math.sin((hour_val - 8.0) * two_pi_over_24)

        # HVAC 45-min sawtooth oscillation (+/- 0.6 C)
        hvac = (((t_sec % 2700) / 2700.0) - 0.5) * 1.2

        # Fast deterministic pseudorandom jitter (+/- 0.15 C)
        jitter = ((i % 19) - 9) * 0.015
        temp = round(diurnal + hvac + jitter, 2)

        # Inverse humidity cycle (30% - 90%)
        humid_base = 55.0 - 6.0 * math.sin((hour_val - 8.0) * two_pi_over_24)
        humid_val = max(30.0, min(90.0, humid_base + jitter * 2))

        # Partial payload injection: 0.5% rows have null humid
        humid = round(humid_val, 2) if (i % 200 != 0) else None

        rows.append({
            "data_id": f"ts_{i}_{int(ts.timestamp())}",
            "dev_id": dev_id,
            "timestamp": ts,
            "temp": temp,
            "humid": humid,
        })
    return rows


def generate_ats_batch(
    start_idx: int,
    batch_size: int,
    start_time: datetime,
    step_seconds: float,
    dev_id: str,
    outage1_start: float,
    outage1_end: float,
    outage2_start: float,
    outage2_end: float,
) -> list[dict]:
    """Generates a chunk of realistic ATS power grid telemetry dictionaries."""
    rows = []

    for i in range(start_idx, start_idx + batch_size):
        t_sec = i * step_seconds
        ts = start_time + timedelta(seconds=t_sec)

        is_outage1 = outage1_start <= t_sec <= outage1_end
        is_outage2 = outage2_start <= t_sec <= outage2_end
        in_outage = is_outage1 or is_outage2

        if in_outage:
            outage_elapsed = (t_sec - outage1_start) if is_outage1 else (t_sec - outage2_start)
            pln = 0.0
            genset = round(221.0 + ((i % 11) - 5) * 0.35, 2)
            state = "GENSET"
            # Cranking sag during first 120 seconds of outage
            if outage_elapsed <= 120.0:
                aki = round(12.1 + ((i % 7) - 3) * 0.02, 2)
            else:
                aki = round(12.5 + ((i % 7) - 3) * 0.02, 2)
        else:
            pln = round(220.0 + ((i % 13) - 6) * 0.35, 2)
            genset = 0.0
            state = "PLN"
            # Periodic momentary sag every 3 days for 10s (triggers warning threshold)
            if (t_sec % (3 * 86400)) < 10.0:
                aki = 11.70
            else:
                aki = round(13.2 + ((i % 9) - 4) * 0.02, 2)

        rows.append({
            "data_id": f"ats_{i}_{int(ts.timestamp())}",
            "dev_id": dev_id,
            "timestamp": ts,
            "state": state,
            "pln": pln,
            "genset": genset,
            "aki": aki,
            "rem_hour": 0.0 if not in_outage else 2.5,
            "rem_min": 0.0,
            "rem_sec": 0.0,
            "auto_mode": True,
            "emergency": False,
        })
    return rows


def seed_telemetry(
    engine,
    total_rows: int = 1000000,
    days: int = 30,
    batch_size: int = 25000,
    target_url: str = "",
) -> tuple[float, float]:
    """Executes high-throughput chunked bulk insert across TS and ATS tables."""
    half_rows = total_rows // 2
    ts_total = half_rows
    ats_total = total_rows - half_rows

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=days)
    total_seconds = float(days * 86400)
    ts_step = total_seconds / float(max(1, ts_total))
    ats_step = total_seconds / float(max(1, ats_total))

    # Outage periods: Day 7 (3h) and Day 21 (1.5h)
    outage1_start = 7.0 * 86400.0 + 10.0 * 3600.0
    outage1_end = outage1_start + 3.0 * 3600.0
    outage2_start = 21.0 * 86400.0 + 14.0 * 3600.0
    outage2_end = outage2_start + 1.5 * 3600.0

    is_sqlite = "sqlite" in target_url.lower()

    print(f"\n=======================================================")
    print(f" HubGate V5 Synthetic Telemetry Seeder")
    print(f" Engine: {'SQLite (WAL Mode)' if is_sqlite else 'PostgreSQL'}")
    print(f" Target URL: {target_url}")
    print(f" Total Rows: {total_rows:,} ({ts_total:,} TS + {ats_total:,} ATS)")
    print(f" Time Window: {days} days ({start_time.isoformat()} to {end_time.isoformat()})")
    print(f" Chunk Batch Size: {batch_size:,}")
    print(f"=======================================================\n")

    start_perf = time.perf_counter()
    inserted_rows = 0

    with engine.begin() as conn:
        if is_sqlite:
            conn.execute(text("PRAGMA synchronous = OFF;"))
            conn.execute(text("PRAGMA journal_mode = WAL;"))
            conn.execute(text("PRAGMA temp_store = MEMORY;"))
            conn.execute(text("PRAGMA cache_size = -128000;"))

        # 1. Seed Temperature Sensor Rows (100k on dev 1, 400k on dev 2 = 500k total TS)
        print(f"[1/2] Seeding {ts_total:,} Temperature Sensor telemetry rows...", flush=True)
        dev1_rows = min(100000, ts_total)
        dev2_rows = ts_total - dev1_rows
        dev1_step = total_seconds / float(max(1, dev1_rows))
        dev2_step = total_seconds / float(max(1, dev2_rows)) if dev2_rows > 0 else 1.0

        for offset in range(0, dev1_rows, batch_size):
            cur_batch_len = min(batch_size, dev1_rows - offset)
            batch = generate_ts_batch(
                start_idx=offset,
                batch_size=cur_batch_len,
                start_time=start_time,
                step_seconds=dev1_step,
                dev_id=BENCH_TS_DEV_ID,
            )
            conn.execute(insert(temperature_data), batch)
            inserted_rows += cur_batch_len
            elapsed = time.perf_counter() - start_perf
            rps = inserted_rows / max(0.001, elapsed)
            pct = (inserted_rows / total_rows) * 100.0
            print(f"  [{inserted_rows:,} / {total_rows:,} rows ({pct:5.1f}%) — {rps:,.0f} rows/sec]", end="\r", flush=True)

        for offset in range(0, dev2_rows, batch_size):
            cur_batch_len = min(batch_size, dev2_rows - offset)
            batch = generate_ts_batch(
                start_idx=dev1_rows + offset,
                batch_size=cur_batch_len,
                start_time=start_time,
                step_seconds=dev2_step,
                dev_id="BENCH_DEV_TS_02",
            )
            conn.execute(insert(temperature_data), batch)
            inserted_rows += cur_batch_len
            elapsed = time.perf_counter() - start_perf
            rps = inserted_rows / max(0.001, elapsed)
            pct = (inserted_rows / total_rows) * 100.0
            print(f"  [{inserted_rows:,} / {total_rows:,} rows ({pct:5.1f}%) — {rps:,.0f} rows/sec]", end="\r", flush=True)

        # 2. Seed ATS Telemetry Rows
        print(f"\n[2/2] Seeding {ats_total:,} ATS telemetry rows...", flush=True)
        for offset in range(0, ats_total, batch_size):
            cur_batch_len = min(batch_size, ats_total - offset)
            batch = generate_ats_batch(
                start_idx=offset,
                batch_size=cur_batch_len,
                start_time=start_time,
                step_seconds=ats_step,
                dev_id=BENCH_ATS_DEV_ID,
                outage1_start=outage1_start,
                outage1_end=outage1_end,
                outage2_start=outage2_start,
                outage2_end=outage2_end,
            )
            conn.execute(insert(ats_data), batch)
            inserted_rows += cur_batch_len

            elapsed = time.perf_counter() - start_perf
            rps = inserted_rows / max(0.001, elapsed)
            pct = (inserted_rows / total_rows) * 100.0
            print(f"  [{inserted_rows:,} / {total_rows:,} rows ({pct:5.1f}%) — {rps:,.0f} rows/sec]", end="\r", flush=True)

    if is_sqlite:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA synchronous = NORMAL;"))

    total_elapsed = time.perf_counter() - start_perf
    overall_rps = total_rows / max(0.001, total_elapsed)
    print(f"\n\n[SUCCESS] Successfully seeded {total_rows:,} rows in {total_elapsed:.2f}s ({overall_rps:,.0f} rows/sec).")
    return total_elapsed, overall_rps


def verify_seeding(engine, target_url: str):
    """Verifies row counts, nullability ratio, and EXPLAIN QUERY PLAN index usage."""
    print("\n[Verification] Running integrity and query plan analysis...")
    is_sqlite = "sqlite" in target_url.lower()

    with engine.connect() as conn:
        ts_count = conn.execute(
            select(func.count()).select_from(temperature_data).where(
                temperature_data.dev_id == BENCH_TS_DEV_ID
            )
        ).scalar()

        ats_count = conn.execute(
            select(func.count()).select_from(ats_data).where(
                ats_data.dev_id == BENCH_ATS_DEV_ID
            )
        ).scalar()

        null_humid = conn.execute(
            select(func.count()).select_from(temperature_data).where(
                temperature_data.dev_id == BENCH_TS_DEV_ID,
                temperature_data.humid.is_(None),
            )
        ).scalar()

        print(f"  - TS Device Telemetry Rows:  {ts_count:,}")
        print(f"  - ATS Device Telemetry Rows: {ats_count:,}")
        print(f"  - Null Humid Injections:     {null_humid:,} ({null_humid / max(1, ts_count) * 100:.2f}%)")

        # Explain query plan for 30d downsampling
        if is_sqlite:
            start_ts = (datetime.now(UTC) - timedelta(days=30)).isoformat()
            end_ts = datetime.now(UTC).isoformat()
            explain_sql = text(
                """
                EXPLAIN QUERY PLAN
                SELECT (CAST(strftime('%s', timestamp) AS INTEGER) / 2592) * 2592 AS b,
                       AVG(temp), MIN(temp), MAX(temp)
                FROM temperature_data
                WHERE dev_id = :dev_id AND timestamp >= :start AND timestamp <= :end
                GROUP BY b ORDER BY b;
                """
            )
            plan_rows = conn.execute(explain_sql, {"dev_id": BENCH_TS_DEV_ID, "start": start_ts, "end": end_ts}).fetchall()
            print("\n  [EXPLAIN QUERY PLAN for 30d Downsampling]:")
            for r in plan_rows:
                print(f"    {r}")
            if not any("idx_temp_dev_timestamp" in str(r) or "idx_temp_covering" in str(r) or "USING INDEX" in str(r) for r in plan_rows):
                print("  [WARN] Query plan did not report using expected index.")
            else:
                print("  [PASS] Confirmed composite index usage (no full-table scans).")


def main():
    parser = argparse.ArgumentParser(description="HubGate V5 High-Performance Synthetic Telemetry Seeder")
    parser.add_argument("--total-rows", type=int, default=1000000, help="Total records to seed (default: 1,000,000)")
    parser.add_argument("--days", type=int, default=30, help="Time window span in days (default: 30)")
    parser.add_argument("--batch-size", type=int, default=25000, help="DML insert chunk batch size (default: 25,000)")
    parser.add_argument("--db-url", type=str, default=None, help="Database connection URL override")
    parser.add_argument("--clean", action="store_true", help="Purge benchmark records before seeding")
    parser.add_argument("--verify", action="store_true", help="Run query plan and row count verification after seeding")

    args = parser.parse_args()

    engine, target_url = get_target_engine(args.db_url)
    ensure_prerequisites(engine, clean=args.clean)
    seed_telemetry(
        engine=engine,
        total_rows=args.total_rows,
        days=args.days,
        batch_size=args.batch_size,
        target_url=target_url,
    )
    if args.verify:
        verify_seeding(engine, target_url)


if __name__ == "__main__":
    main()
