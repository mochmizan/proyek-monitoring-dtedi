# AGENTS.md — server (HubGate V5)

## Purpose

FastAPI cloud gateway (HubGate V5) — ingestion, auth/RBAC, rooms/devices/alerts API, and telemetry pipeline for IoT fleet. Code lives in `server/`.

## Ownership

- **server/** owns HubGate V5: FastAPI app, DB models/migrations, auth, services, and gateway API.
- Owned by root AGENTS.md for repo-wide DOX and global rules.

## Local Contracts

### Stack & Database Engine Architecture

Python 3.14, FastAPI 0.136.1, Uvicorn 0.46.0, Pydantic 2.13.3, SQLAlchemy 2.0.49, Alembic, PostgreSQL 16 (prod) + SQLite 3 WAL fallback (`DATABASE_URL` unset), SlowAPI 0.1.10, argon2-cffi 25.1.0, psycopg2-binary 2.9.12, python-multipart 0.0.27, APScheduler 3.10.4 + tzdata (Asia/Jakarta) — all pinned `==` in `requirements.txt`.

- **Production Target Database**: PostgreSQL 16 (hosted on VPS 10.33.102.172 / 100.108.98.30). High-concurrency MVCC multi-writer architecture. Bounded connection pool (`pool_size=10, max_overflow=5, pool_recycle=1800, pool_pre_ping=True`), with 15s server `statement_timeout` (`-c statement_timeout=15000`).
- **Local Dev & Edge Lab Database**: SQLite 3 (WAL mode) with a documented single-writer ceiling. Connect-time PRAGMAs configured via SQLAlchemy event listener in `databasev5.py`:
  - `PRAGMA journal_mode = WAL;` (concurrent readers do not block writers)
  - `PRAGMA busy_timeout = 10000;` (10s lock timeout prevents immediate busy errors)
  - `PRAGMA synchronous = NORMAL;` (durable WAL mode disk sync)
  - `PRAGMA foreign_keys = ON;` (strict relational constraint enforcement)
  - `PRAGMA temp_store = MEMORY;` (in-memory temporary tables)
  - `PRAGMA cache_size = -64000;` (64MB memory page cache)
  - `PRAGMA mmap_size = 268435456;` (256MB memory-mapped I/O)
- **Session Management (`get_db`)**: FastAPI dependency generator in `databasev5.py` providing request-scoped sessions with automatic `db.rollback()` on exceptions and guaranteed `db.close()` in `finally`.

### Entry & Architecture

- Entry: `hubgatev5.py` shim re-exports `api` from `app/main.py`; run via `uvicorn hubgatev5:api --host 127.0.0.1 --port 8000` (prod behind Nginx 443). Canonical assembly at `app/main.py` (CORS, rate limiter, scheduler `lifespan`, presence worker lifespan, `GET /health` + `/api/health` unauthenticated DB `SELECT 1` check, static mount).
- Routers: `app/routers/` — `auth`, `hubs`, `rooms` (single SQL outerjoin list; indexed room map with AC operational state merging), `devices` (downsampling v2 history; idempotent read-only single/list detail with `selectinload`), `alerts`, `iot` (single & batch ingestion with deterministic UUIDs, auth double-commit elimination, lock-free auth cache, and dialect-specific ON CONFLICT DO NOTHING), `commands` (`GET /api/commands/{command_id}` delivery status check), `schedules`.
- Core: `app/core/config`, `app/core/rate_limit`, `app/core/logging`.
- Services: `app/services/alert_engine`, `app/services/presence` (5s background presence worker `evaluate_device_presence_batch`), `app/services/scheduler` (APScheduler `BackgroundScheduler` `Asia/Jakarta` cron → `pending_commands`).
- DB: `app/modelsv5.py`; Alembic at `alembic/`; `init_sqlv5.py` is idempotent additive migration for fallback.

### Tables & Composite Indexes

`hub_table`, `rooms`, `dev_table`, `device_threshold_config`, `data_table`, `event_log`, `temperature_data`, `ats_data`, `pending_commands`, `schedules`, `users`, `sessions`, `login_attempts`.

Composite SARGable performance indexes:
- `ix_event_log_dev_metric_ts`: `event_log(dev_id, metric, timestamp.desc())` (threshold debounce lookups)
- `ix_dev_table_hub_id`: `dev_table(hub_id)` (hub foreign key relationship joins)
- `ix_pending_commands_hub_status_created`: `pending_commands(hub_id, status, created_at)` (edge command polling queue)
- `idx_temp_dev_timestamp`: `temperature_data(dev_id, timestamp.desc())` (SARGable history scans)
- `idx_ats_dev_timestamp`: `ats_data(dev_id, timestamp.desc())` (SARGable ATS history scans)

### Downsampling V2 & Telemetry History Contract

- Endpoint: `GET /api/devices/{id}/history` (`?range=6h,24h,7d,30d,all&max_points=1000`).
- Dynamic Bucket Resolution: Calculates bucket size in seconds dynamically based on requested time range and `max_points` parameter.
- Single-Pass SQL Bucket Expression (`_build_epoch_bucket_expr`):
  - SQLite: `func.unixepoch(col)` integer seconds (~2x faster than strftime).
  - PostgreSQL: `CAST(FLOOR(EXTRACT(epoch FROM timestamp) / bucket_seconds) * bucket_seconds AS INTEGER)`.
- Min/Max Envelopes: Computes `AVG`, `MIN`, `MAX` envelope bounds in the same single-pass query (`temp`/`temp_min`/`temp_max`, `humid`/`humid_min`/`humid_max`, `pln`/`genset`/`aki` min/max).
- Output Bounds: Result length strictly bounded `total_points <= max_points` (or `max_points + 5` bucket alignment tolerance). Sub-1000 rows returned unaggregated in ascending order.
- Read SLA: 30d history downsample P95 < 300ms (PostgreSQL production target).

### Batch Ingestion Pipeline Contract

- Endpoints: `POST /api/iot` (single point) and `POST /api/iot/batch` (up to 1000 points/batch via `IotBatchRequest` or list).
- Auth Double-Commit Elimination: `verify_hub_identity` stages heartbeats (`stage_hub_heartbeat`) without committing to the DB session; telemetry and heartbeat commit atomically in endpoint handlers.
- Lock-Free `HubAuthCache` (30s Throttle): Thread-safe fast path reads without acquiring mutex; acquires lock only on cache miss, timestamp update, or invalidation; throttles heartbeat DB persistence to once per 30s per hub.
- Deterministic ID Generation: `data_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{dev_id}:{ts.isoformat()}"))` to guarantee replay idempotency across edge retries.
- Dialect-Specific Bulk Upsert: `bulk_insert_or_ignore` uses `ON CONFLICT (dev_id, timestamp) DO NOTHING` on PostgreSQL and `on_conflict_do_nothing` (with fallback to SQLite `OR IGNORE`) on SQLite WAL.
- In-Batch Deduplication: Filters approved devices via bulk query, deduplicates points by `(dev_id, timestamp)` in memory before bulk insertion.
- Batch Alert Storm Suppression: Evaluates threshold alerts and presence recovery only once per unique device using its latest reading in the batch (`latest_reading_per_dev`).
- Write Path SLAs:
  - `POST /api/iot` single-write latency: P95 < 200ms, P99 < 500ms.
  - `POST /api/iot/batch` batch-write latency: P95 < 350ms, P99 < 750ms.
  - Ingestion throughput > 500 points/sec with 0 database locked errors.

### Background Presence Sweeper & Read-Only Invariant

- Lifespan Worker: `app/services/presence.py` runs a 5s background worker (`evaluate_device_presence_batch`) sweeping devices where `now_utc - last_seen > 25s`, setting `last_status = 'offline'` and logging `DEVICE_OFFLINE` alerts; auto-resolves alerts when online; prunes stale unapproved devices older than 25s; runs in an isolated scoped `SessionLocal()` with rollback protection.
- Idempotent Read-Only Invariant: `GET /api/devices`, `GET /api/rooms`, `GET /api/rooms/{id}/map` perform exactly 0 database write operations for user queries. Device status is derived purely in memory on read. `GET /api/devices` uses `selectinload(dev_table.threshold_config)` and `selectinload(dev_table.room)` preventing N+1 queries.
- Optimized Room Queries: `list_rooms` executes exactly 1 SQL outer join query with `func.count(dev_table.dev_id)` and group by. `get_room_map` executes sub-millisecond indexed queries (`timestamp.desc()` leveraging composite SARGable indexes `idx_temp_dev_timestamp`, `idx_ats_dev_timestamp`), with AC operational state merging (combining `temperature_data` ambient temp/humidity with `data_table` `AC1_POWER`, `AC1_TEMP`, `AC2_POWER`, `AC2_TEMP`).

## Work Guidance

- New device types: extend discriminated union in `schemasv5.py` (`DEV_TYPE` literal + new model), keep `model_validator` + `ValidationInfo` pattern for DB-aware validation.
- New endpoints: add SlowAPI `limiter` decorator + auth dependency (`require_role` or hub header).
- Keep `JSONB().with_variant(JSON, "sqlite")` for Postgres/SQLite compat.
- Keep tests green: all 179 tests run cleanly via `pytest server/ -q`.

## Verification

- `pytest server/ -q` — runs all 179 test cases covering engine hardening, downsampling v2, schema indexing, batch ingestion, read-only presence, room map query optimization, and benchmark verification.
- `python tools/seed_benchmark_telemetry.py --total-rows 1000000 --days 30 --clean --verify` — seeds 1,000,000 synthetic rows in ~60s and verifies composite index query plans.
- `python tools/benchmark_concurrency_stress.py` — executes 15s multi-worker stress test validating all read, write, throughput, and zero-lock SLAs.

## Child DOX Index

| Path | Scope |
|---|---|
| — | No child DOX; `server/` is a leaf. |
