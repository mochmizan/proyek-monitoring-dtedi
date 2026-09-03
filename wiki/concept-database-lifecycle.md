---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/entity-security-auth.md, wiki/concept-telemetry-pipeline.md, wiki/concept-downsampling-v2.md, wiki/concept-presence-engine.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/databasev5.py, server/modelsv5.py, server/init_sqlv5.py, server/alembic/env.py, server/alembic/versions/04a48dbce60b_initial_schema_as_observed.py, server/alembic/versions/b7c9e2f1a4d8_add_schedules.py, server/alembic/versions/c1a8b9f0e2d3_schema_indexing_and_nullability.py, server/app/dependencies.py, server/app/services/presence.py, server/app/services/scheduler.py, server/app/services/telemetry.py, server/app/routers/iot.py, server/app/routers/devices.py, server/app/routers/rooms.py, server/auth.py]
updated: 2026-09-03
---

# HubGate V5 Database Lifecycle & Persistence Architecture

HubGate V5 persists high-frequency time-series telemetry, device inventory, relational hierarchy (hubs, rooms, devices), operational events, scheduled automation jobs, and user sessions. The persistence layer in `server/databasev5.py` operates a dual-dialect engine architecture supporting **PostgreSQL 16** for multi-writer production VPS deployments and **SQLite 3 WAL** for single-node edge and development environments.

```mermaid
flowchart TD
    subgraph Clients
        FastAPIThreads["FastAPI Worker Pool (AnyIO: ~40 Threads)"]
        BackgroundTasks["APScheduler Worker Threads (Presence Sweeper, Cron Jobs)"]
    end

    subgraph "Session Factory & Scoping"
        GetDB["get_db() Dependency (Per-Request Scoped)"]
        WorkerDB["SessionLocal() Scoped Instance (Per-Task Scoped)"]
    end

    subgraph "SQLAlchemy Engine Architecture"
        DialectRouter{"Dialect Check: DATABASE_URL"}
        PGPool["PostgreSQL QueuePool<br/>pool_size: 10, max_overflow: 5<br/>statement_timeout: 15s<br/>pool_recycle: 1800s"]
        SQLiteEngine["SQLite Engine (WAL Mode)<br/>timeout: 10s, check_same_thread: False<br/>Connect Listener: 7 PRAGMAs"]
    end

    subgraph "Target Databases"
        PostgreSQL[("PostgreSQL 16 (Production Target)<br/>MVCC, Row-Level Locks, JSONB")]
        SQLite[("SQLite 3 (Edge / Dev Target)<br/>Single-Writer WAL, Shared Mem")]
    end

    FastAPIThreads --> GetDB
    BackgroundTasks --> WorkerDB

    GetDB --> DialectRouter
    WorkerDB --> DialectRouter

    DialectRouter -- postgresql:// --> PGPool
    DialectRouter -- sqlite:/// --> SQLiteEngine

    PGPool --> PostgreSQL
    SQLiteEngine --> SQLite
```

---

## 1. Dual-Dialect Engine & Connection Pool Architecture

The database engine is instantiated via `get_engine_kwargs(DATABASE_URL)` in `server/databasev5.py`, configuring distinct pooling, query timeout, and driver parameters based on the connection scheme.

### PostgreSQL 16 (Production Target)
- **Deployment Host**: Dedicated VPS instances (`10.33.102.172` / `100.108.98.30`).
- **Connection Pool Bounds (`QueuePool`)**:
  - `pool_size = 10` (default, overridable via `DB_POOL_SIZE`): Baseline persistent connection pool maintained across requests.
  - `max_overflow = 5` (`DB_MAX_OVERFLOW`): Upper limit of temporary burst connections created under surge traffic. Total connection ceiling is 15.
  - `pool_recycle = 1800` (`DB_POOL_RECYCLE`): Automatically tears down and recreates connections every 30 minutes to prevent server-side TCP timeout drops.
  - `pool_pre_ping = True`: Emits a lightweight `SELECT 1` heartbeat prior to checking out a connection, proactively evicting broken sockets.
- **Statement Timeout Guard**:
  - Configured via connection options: `-c statement_timeout=15000` (15 seconds, overridable via `DB_STATEMENT_TIMEOUT_MS`).
  - Aborts any unindexed or runaway analytics query that exceeds 15 seconds, protecting database workers from connection starvation.
- **Fail-Fast Production Check**: If `ENV=prod` and `DATABASE_URL` is omitted or points to SQLite, HubGate V5 raises `RuntimeError` at module import and halts initialization.

### SQLite 3 WAL Mode (Edge / Local Dev)
- **Driver Tuning**: `check_same_thread = False`, `timeout = 10.0` (client-side driver lock acquisition ceiling).
- **Connection-Time PRAGMA Listener**: Attached via SQLAlchemy `@event.listens_for(engine, "connect")`:
  - `PRAGMA journal_mode = WAL;`: Write-Ahead Logging allows concurrent readers to query snapshots while a single writer thread operates without blocking reads.
  - `PRAGMA busy_timeout = 10000;`: Configures a 10-second wait before raising `sqlite3.OperationalError: database is locked`.
  - `PRAGMA synchronous = NORMAL;`: Safely minimizes disk sync flushes to WAL checkpoints, improving write IOPS while maintaining durability against power loss or crashes.
  - `PRAGMA foreign_keys = ON;`: Enforces relational integrity (`ON DELETE CASCADE` on child tables).
  - `PRAGMA temp_store = MEMORY;`: In-memory temporary tables and sorting buffers.
  - `PRAGMA cache_size = -64000;`: Allocates 64MB memory page cache.
  - `PRAGMA mmap_size = 268435456;`: Allocates 256MB memory-mapped file access.

### Connection Sizing & Pool Starvation Analysis
- **Worker-to-Connection Ratio**: FastAPI executes synchronous endpoint handlers (`def`) in AnyIO's threadpool, which defaults to 40 worker threads. Additionally, APScheduler runs background threads (presence sweeper every 5 seconds, schedule jobs, etc.).
- **Starvation Risk**: If 20 concurrent HTTP requests arrive simultaneously while the background sweeper runs, 15 database connections (`pool_size=10 + max_overflow=5`) are checked out immediately. The remaining 5 requests block waiting for a connection checkout. SQLAlchemy's default checkout timeout is 30 seconds.
- **Timeout Inversion**: If a connection wait lasts up to 30 seconds while `statement_timeout` is 15 seconds, client requests time out waiting for connection checkout rather than during query execution.
- **Remediation**: For production deployments expecting $\ge 50$ concurrent clients, scale `DB_POOL_SIZE` to 25 and `DB_MAX_OVERFLOW` to 15, matching the AnyIO worker thread pool.

---

## 2. Database Session Lifecycle & Transaction Scoping

FastAPI route handlers and background tasks adhere to explicit session scoping to ensure transaction atomicity and prevent connection checkout leaks:

```mermaid
sequenceDiagram
    autonumber
    participant Request as Incoming HTTP Request
    participant Dep as get_db() Dependency
    participant Handler as Route Handler
    participant DB as SQLAlchemy Session
    
    Request->>Dep: Invoke get_db()
    Dep->>DB: SessionLocal() checkout
    Dep->>Handler: yield db session
    alt Successful Execution
        Handler->>DB: Stage entities & db.commit()
        Handler-->>Request: HTTP 200 / 201 Response
    else Unhandled Exception Raised
        Handler-->>Dep: Exception propagates
        Dep->>DB: db.rollback()
    end
    Dep->>DB: db.close() (Guaranteed checkout return)
```

### Request-Scoped Session Dependency (`get_db`)
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```
- **Automatic Rollback**: Any unhandled exception (HTTPException, validation error, database error) triggers an immediate rollback, preventing dirty session states from contaminating subsequent queries.
- **Deterministic Resource Teardown**: The `finally: db.close()` block guarantees that connection checkouts are returned to the pool even during process aborts or client disconnections.

### The Single Atomic Commit Invariant
In earlier iterations, helper dependencies or secondary services performed intermediate commits (e.g. `verify_hub_identity` committing `hub.last_seen`), creating lock collisions (CRIT-01) and leaving orphaned records on failures. In HubGate V5:
1. **Dependency Staging**: Dependencies only mutate ORM entity state in memory (`stage_hub_heartbeat`).
2. **Atomic Ingestion Commit**: In `POST /api/iot` and `POST /api/iot/batch`, hub heartbeat update, telemetry record insertion (`bulk_insert_or_ignore`), presence state update (`resolve_offline_on_telemetry`), and alert evaluation (`evaluate_device_thresholds`) commit in a single, unified `db.commit()` call.
3. **Idempotent Bulk Upsert**: `bulk_insert_or_ignore` inserts records in chunks of 500 (`chunk_size=500` to remain safely below SQLite variable binding limits) using `ON CONFLICT (dev_id, timestamp) DO NOTHING` on PostgreSQL and SQLite, ensuring WAL replays cause no duplicates or rollbacks.
4. **Device Ownership Enforcement (`SEC-06`)**: Prior to staging or inserting records, `receive_iot` and `receive_iot_batch` verify that `device.hub_id == hub.hub_id`. Telemetry from an unassociated device is rejected (HTTP 403 in single ingest, or skipped with incremented `ignored_count` in batch ingest) with security warning logging, executing zero database write operations for unauthorized payloads.

### Background Worker Session Discipline
Background tasks run in independent, isolated database sessions to prevent cross-thread session bleeding:
- **Presence Sweeper (`evaluate_device_presence_batch`)**: Scheduled every 5 seconds. Opens `db = SessionLocal()`, executes batch scans, prunes stale pending nodes with a bulk `delete()`, commits state transitions, and guarantees `finally: db.close()`.
- **APScheduler Execution (`fire_schedule`)**: Triggered by cron triggers. Opens a fresh `SessionLocal()`, inserts `pending_commands`, updates `schedules.next_run_at`, commits, and closes the session.

### Session Sliding Window Throttling (`SEC-10`) & Write-on-Read Elimination
Previously, every request authenticated via session cookie in `server/auth.py` executed `UPDATE sessions SET expires_at = ...` and `db.commit()`. On SQLite WAL, this forced an EXCLUSIVE write lock on every GET request, transforming concurrent read traffic into a serialized write bottleneck.

This is resolved via **Sliding Window Throttling**:
- `verify_session` inspects `remaining_validity = expires_at - now`.
- A database write transaction and `db.commit()` are executed **only** if `remaining_validity < timedelta(minutes=90)`.
- Inbound requests with fresh sessions ($\ge 90$ minutes remaining) skip the database write completely.
- This eliminates the write-on-read lock in SQLite WAL and dramatically reduces UPDATE churn and VACUUM pressure in PostgreSQL.

---

## 3. Concurrency Mechanics: PostgreSQL 16 vs SQLite 3 WAL

| Architectural Dimension | PostgreSQL 16 (Production) | SQLite 3 WAL (Local / Edge) |
|---|---|---|
| **Concurrency Model** | Multi-writer MVCC (Multi-Version Concurrency Control) with row-level locks. | Single-writer serialization with multi-reader WAL concurrency. |
| **Write Lock Contention** | Near-zero between distinct rows; transactions commit concurrently across connections. | Concurrent writers block until the active writer commits or 10s `busy_timeout` expires. |
| **Connection Pooling** | `QueuePool` with bounded sizing (`pool_size=10, max_overflow=5`). | Thread-local connections via `NullPool` or `SingletonThreadPool` with `timeout=10.0s`. |
| **JSON Storage Engine** | Binary JSON (`JSONB`), supporting native GIN indexing and expression extraction. | Text JSON (`JSON`), parsed dynamically on read. Configured via `JSONB().with_variant(JSON, "sqlite")`. |
| **Timestamp Semantics** | `TIMESTAMP WITH TIME ZONE` stores native aware UTC timestamps. | String-based `TIMESTAMP` returning naive UTC datetimes, requiring defensive timezone normalization. |
| **Variable Binding Limits** | 65,535 parameters per query. | 999 parameters (SQLite < 3.32) or 32,766 (modern SQLite). Bounded by 500 chunking. |
| **Epoch Downsampling Math** | `CAST(FLOOR(EXTRACT(epoch FROM col) / bucket_seconds) * bucket_seconds AS INTEGER)` | `(CAST(func.unixepoch(col) / bucket_seconds, Integer) * bucket_seconds)` |
| **Unique Constraint Backing** | Backed by PostgreSQL B-tree unique index `ON CONFLICT (dev_id, timestamp)`. | Backed by SQLite unique index with automatic startup duplicate deduplication. |

---

## 4. Migration Discipline, Dual-Path Architecture & Drift Risks

HubGate V5 currently maintains two distinct schema migration mechanisms: an Alembic migration chain and imperative runtime migration routines in `server/init_sqlv5.py`.

```mermaid
graph TD
    subgraph "Alembic Version Chain (alembic/versions/)"
        A0["04a48dbce60b<br/>(initial_schema_as_observed)"] --> A1["b7c9e2f1a4d8<br/>(add_schedules)"]
        A1 --> A2["c1a8b9f0e2d3<br/>(schema_indexing_and_nullability)"]
    end
    
    subgraph "Runtime Imperative Migrations (init_sqlv5.py)"
        R0["try_alembic_upgrade()"] --> R1["migrate_dev_table_hub_name_to_hub_id()"]
        R1 --> R2["migrate_additive_columns()"]
        R2 --> R3["Base.metadata.create_all()"]
        R3 --> R4["migrate_indexes()"]
    end
    
    A2 -.-> R0
```

### Alembic Migration Inventory
1. `04a48dbce60b_initial_schema_as_observed.py`: Base migration representing observed state.
2. `b7c9e2f1a4d8_add_schedules.py`: Adds `schedules` table with dialect-aware JSON/JSONB column and composite indexes.
3. `c1a8b9f0e2d3_schema_indexing_and_nullability.py`: Converts `temperature_data` (`temp`, `humid`) to `nullable=True` and applies composite SARGable performance indexes across `event_log`, `dev_table`, `pending_commands`, and `data_table`.

### Identified Production Migration Gaps & Drift Risks

#### MIG-01: Non-Deterministic Initial Alembic Revision
- **Mechanism**: In `04a48dbce60b`, `upgrade()` executes `Base.metadata.create_all(bind=bind)`.
- **Drift Risk**: `create_all` inspects the live Python ORM definitions in `modelsv5.py` at execution time rather than applying fixed DDL operations. If new models are added, running migrations from scratch will create all tables up-front, rendering subsequent Alembic revisions redundant or causing collision errors on incremental upgrades.

#### MIG-02: Dual-Path Migration Conflict
- **Mechanism**: `server/init_sqlv5.py` and `databasev5.migrate_indexes()` run raw imperative SQL scripts on gateway startup (`init_db()`, `scheduler_lifespan`), altering columns (`migrate_additive_columns`) and creating indexes (`migrate_indexes`).
- **Drift Risk**: Schema alterations occur outside the `alembic_version` tracking table. Automated CI or production deployment pipelines running `alembic upgrade head` can drift out of synchronization with nodes initialized via `init_sqlv5.py`.

#### MIG-03: Asymmetric In-Database Deduplication
- **Mechanism**: `init_sqlv5.migrate_indexes()` executes duplicate pruning before creating unique constraints:
  ```sql
  DELETE FROM tbl WHERE rowid NOT IN (SELECT MIN(rowid) FROM tbl GROUP BY dev_id, timestamp)
  ```
- **Drift Risk**: The query is guarded by `dialect.name == "sqlite"` because PostgreSQL does not have a `rowid` pseudocolumn. On PostgreSQL, if duplicate `(dev_id, timestamp)` records exist prior to applying unique constraints, unique index creation fails with `IntegrityError` without fallback deduplication.

#### MIG-04: Missing Unique Constraints in Alembic Migrations
- **Mechanism**: While composite lookup indexes were migrated in `c1a8b9f0e2d3`, unique indexes `uq_temp_dev_timestamp`, `uq_ats_dev_timestamp`, and `uq_data_dev_timestamp` were omitted from Alembic revision `c1a8b9f0e2d3`. They are only created via `init_sqlv5.py:migrate_indexes()`.
- **Drift Risk**: Deployments executing strictly `alembic upgrade head` lack the unique constraints required to support PostgreSQL and SQLite `ON CONFLICT DO NOTHING` statements in `bulk_insert_or_ignore`, causing bulk telemetry ingestion to fail with syntax or integrity errors.

---

## 5. High-Throughput Query Patterns & SARGable Optimization

HubGate V5 eliminates table-wide linear scans by aligning queries with composite B-tree indexes:

### 1. Downsampling V2 Epoch Bucketing
- **Path**: `GET /api/devices/{id}/history`
- **Pattern**: Evaluates time spans (6h to 30d) in a single SQL pass:
  ```sql
  SELECT 
      CAST(FLOOR(EXTRACT(epoch FROM timestamp) / :bucket_sec) * :bucket_sec AS INTEGER) AS bucket_ts,
      AVG(temp) AS temp, MIN(temp) AS temp_min, MAX(temp) AS temp_max,
      AVG(humid) AS humid, MIN(humid) AS humid_min, MAX(humid) AS humid_max
  FROM temperature_data
  WHERE dev_id = :dev_id AND timestamp BETWEEN :start AND :end
  GROUP BY bucket_ts ORDER BY bucket_ts ASC;
  ```
- **Index Utilized**: `idx_temp_dev_timestamp(dev_id, timestamp DESC)` and `idx_ats_dev_timestamp(dev_id, timestamp DESC)`. B-tree prefix match isolates the device, while range scan extracts time boundaries without reading extraneous data.

### 2. Room Sparklines Two-Pass CTE
- **Path**: `GET /api/rooms/sparklines`
- **Pattern**: A single-query two-pass Common Table Expression (CTE). Pass 1 aggregates per-device averages into `device_bucket_agg`; Pass 2 groups by room and calculates room `MAX` envelopes for temperature and humidity, eliminating N+1 queries across facility rooms.

### 3. Batched Device Latest Reading (`get_latest_readings_for_devices`)
- **Path**: Shared service used by `GET /api/devices` and `GET /api/rooms/{id}/map`.
- **Pattern**: Replaces iterative per-device queries with 3 set-based subquery joins (for TS, ATS, and AC controllers):
  ```sql
  SELECT t.* FROM temperature_data t
  JOIN (
      SELECT dev_id, MAX(timestamp) AS max_ts 
      FROM temperature_data 
      WHERE dev_id IN (:dev_ids) 
      GROUP BY dev_id
  ) sub ON t.dev_id = sub.dev_id AND t.timestamp = sub.max_ts;
  ```
- **Performance**: Fetches the latest live state for 100 devices in under 5ms.

### 4. Eager Loading Invariants
- `GET /api/devices` explicitly loads relations via `selectinload(dev_table.threshold_config)` and `selectinload(dev_table.room)`, eliminating lazy-load connection churn during response serialization.
- `GET /api/rooms/{id}/map` loads paired devices using `joinedload(rooms.devices)` in a single database round-trip.
