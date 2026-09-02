---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-data-model.md, wiki/entity-hubbrain-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-downsampling-v2.md, wiki/concept-presence-engine.md, wiki/concept-command-path.md, wiki/concept-alert-engine.md, wiki/concept-time-conventions.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/app/main.py, server/databasev5.py, server/app/dependencies.py, server/app/routers/iot.py, server/app/routers/devices.py, server/app/routers/rooms.py, server/app/services/presence.py, server/app/services/scheduler.py, server/schemasv5.py, server/AGENTS.md, commit:8f8f6cd, commit:9961f5c, commit:35708e4]
updated: 2026-09-02
---

# HubGate V5 (server/)

HubGate V5 is the FastAPI cloud gateway of the smsb stack, living in `server/`. It terminates telemetry ingestion from edge hubs, serves the dashboard API (rooms, devices, alerts, schedules, commands), and manages authentication, access control, and database persistence.

Assembly lives in `server/app/main.py` (the `hubgatev5.py` at the package root is a backwards-compatible shim re-exporting `api`). Routers split by domain: `auth`, `hubs`, `rooms`, `devices`, `alerts`, `iot`, `commands`, and `schedules`. Business logic is encapsulated in services: `alert_engine` (threshold and ATS emergency evaluation on ingest), `presence` (decoupled background presence evaluation), and `scheduler` (APScheduler `BackgroundScheduler` in Asia/Jakarta timezone).

## Database Engine Architecture & Connection Pooling

The database engine in `server/databasev5.py` supports dual-dialect operations with strict resource guards:
- **PostgreSQL 16 (Production Target)**: Hosts VPS deployments (`10.33.102.172` / `100.108.98.30`) with bounded connection pooling (`pool_size=10, max_overflow=5, pool_recycle=1800, pool_pre_ping=True`) and an enforced 15-second statement timeout (`-c statement_timeout=15000`) preventing runaway queries from exhausting database connections.
- **SQLite 3 WAL (Edge / Dev Target)**: Configured with connect-time PRAGMAs:
  - `journal_mode = WAL`: Concurrently allows multiple readers while a single writer operates.
  - `busy_timeout = 10000`: 10-second wait before raising database locked exceptions, eliminating lock collisions during concurrent bursts.
  - `synchronous = NORMAL`: Safely reduces disk sync operations without compromising transaction durability in WAL mode.
  - `foreign_keys = ON`: Enforces relational integrity.
  - `temp_store = MEMORY`, `cache_size = -64000` (64MB memory page cache), and `mmap_size = 268435456` (256MB memory mapping).

Engine connections use `timeout=10.0` and `check_same_thread=False`. FastAPI routes consume sessions via `get_db()`, guaranteeing per-request transaction scoping, automatic exception rollback, and deterministic session closure.

## Throttled Hub Authentication (`HubAuthCache`)

Hub identity verification is managed in `server/app/dependencies.py` via `HubAuthCache`:
- Implements an in-memory, thread-safe cache with double-checked locking and a lock-free read path for high-throughput authentication.
- Throttles heartbeat persistence to 30.0 seconds (`throttle_seconds=30.0`). Incoming requests read cached credentials without locking.
- Solves the critical auth double-commit flaw (CRIT-01): `verify_hub_identity` no longer commits `last_seen` independently. Instead, `stage_hub_heartbeat` marks the hub instance dirty in memory, allowing the endpoint handler to commit heartbeat, telemetry, presence, and alert records in a single atomic transaction.

## Telemetry Ingestion Pipeline

Telemetry lands at either single-item `POST /api/iot` or high-throughput batch `POST /api/iot/batch`:
- `POST /api/iot`: Ingests single telemetry payloads with rate limiting (`120/minute`). Evaluates discriminated unions (`TSData`, `ATSData`, or generic payload), resolves offline state, logs telemetry, and evaluates threshold rules in a single atomic database commit.
- `POST /api/iot/batch`: Accepts up to 1000 records per batch via `IotBatchRequest` or item lists. Executes bulk active-device lookups (`dev_id IN (...)`), filters in-batch duplicates, and inserts in chunks of 500 using `bulk_insert_or_ignore` (`ON CONFLICT DO NOTHING` on PostgreSQL and SQLite).
- Replay Idempotency: All records receive deterministic identifiers `data_id = uuid5(NAMESPACE_OID, f"{dev_id}:{event_time.isoformat()}")`, ensuring replay of edge WAL buffers causes zero duplicate rows or rollback errors.
- Alert Suppression: In batch ingestion, threshold alerts and presence recovery are evaluated strictly once per device on its latest reading, eliminating alert storms during WAL replay recovery.

## Device History & Downsampling V2

Device history (`GET /api/devices/{id}/history`) implements [concept-downsampling-v2.md](concept-downsampling-v2.md):
- Dynamically calculates bucket duration $\Delta T // \text{max\_points}$ over requested time spans (e.g. 6h, 24h, 7d, 30d).
- Groups data in a single SQL pass using native C-level integer epoch math (`unixepoch(timestamp)` on SQLite 3.38+, `extract(epoch from timestamp)` on PostgreSQL 16).
- Computes both average values and exact min/max envelopes (`temp_min`/`temp_max`, `pln_min`/`pln_max`, `aki_min`/`aki_max`), capturing electrical surges and transient dips without signal smoothing.
- Sub-1000 Bypass: Requests spanning $\le 1000$ points bypass grouping and return exact raw telemetry.
- Bounded to `max_points` (default 1000) with 30-day queries executing in < 300ms on PostgreSQL and < 1000ms on SQLite (measured 891.28ms P95).

## Decoupled Presence Sweeper

Device connectivity monitoring is handled by a dedicated background sweeper (`app/services/presence.py`):
- Scheduled every 5 seconds (`PRESENCE_INTERVAL_SECONDS = 5`) via APScheduler.
- Scans active devices in an isolated database session. Devices with no telemetry for > 25 seconds transition to `offline` and log `DEVICE_OFFLINE` alerts; returning devices transition to `online` and resolve open alerts.
- Bounded SLA: Disconnection detection latency is guaranteed within 30 seconds (25s timeout + 5s polling cycle).
- Read-Only Invariant: Read endpoints (`GET /api/devices`, `GET /api/rooms`, `GET /api/rooms/{id}/map`) execute 0 database writes, computing statuses dynamically in memory and eliminating read/write lock contention.

## Administrative Operations & Sessions

- Admin hub deletion: `DELETE /api/hubs/{hub_id}` allows hard-deleting decommissioned hubs (409 Conflict if active devices remain paired; associated room links are set to `NULL`).
- Authentication: Argon2id password hashing, 2h sliding / 12h absolute sessions stored in `sessions` table and delivered via httpOnly, Secure, SameSite=Lax cookies.
- Rate limiting: SlowAPI keyed by client IP (`X-Real-IP` or first component of `X-Forwarded-For`).
- Datetime Contract: All serialized timestamps follow ISO-8601 UTC with explicit timezone offsets (see [concept-time-conventions.md](concept-time-conventions.md)).
