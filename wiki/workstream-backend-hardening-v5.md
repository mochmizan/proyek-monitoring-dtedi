---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-downsampling-v2.md, wiki/concept-telemetry-pipeline.md, wiki/concept-presence-engine.md, wiki/concept-alert-engine.md]
sources: [server/databasev5.py, server/app/dependencies.py, server/app/routers/devices.py, server/app/routers/iot.py, server/app/routers/rooms.py, server/app/services/presence.py, tools/benchmark_concurrency_stress.py, tools/seed_benchmark_telemetry.py, git:notes/benchmarks-baseline.md (archived), commit:8f8f6cd, commit:9961f5c, commit:0fd2e81]
updated: 2026-09-02
---

# Workstream: HubGate V5 Backend Hardening

This workstream details the architectural hardening and optimization of the HubGate V5 FastAPI backend. The initiative eliminated database lock collisions, resolved HTTP 500 query failures under concurrent loads, established high-throughput batch ingestion, implemented Grafana-aligned time-series downsampling, and verified strict performance SLAs across 1,000,000 historical records.

## 1. Six-Phase Architecture & Implementation

| Phase | Domain | Architectural Implementation |
|---|---|---|
| **Phase 1** | Database Engine Hardening & Pool Bounds | Enforced PostgreSQL connection pool boundaries (`pool_size=20, max_overflow=10, pool_recycle=1800, pool_timeout=10`) and a 15-second statement timeout (`-c statement_timeout=15000`). For SQLite 3 WAL, applied connect-time PRAGMAs: `journal_mode=WAL`, `busy_timeout=10000`, `synchronous=NORMAL`, `foreign_keys=ON`, `temp_store=MEMORY`, `cache_size=-8000` (8MB), and `mmap_size=67108864` (64MB). |
| **Phase 2** | Downsampling Query Plan & Aggregation V2 | Engineered single-pass mathematical epoch bucketing ($\Delta T // \text{max\_points}$) in `GET /api/devices/{id}/history`. Implemented native C-level `func.unixepoch(timestamp)` for SQLite 3.38+ (2x speedup over string parsing) and `EXTRACT(epoch FROM timestamp)` for PostgreSQL 16. Aggregated exact min/max envelopes alongside averages, capturing transients while bounding output cardinality to $\le \text{max\_points} + 5$. |
| **Phase 3** | Schema Hardening & SARGable Indexing | Authored Alembic migration `c1a8b9f0e2d3`. Added B-tree composite indexes (`idx_temp_dev_timestamp`, `idx_ats_dev_timestamp`, `ix_event_log_dev_metric_ts`, `ix_dev_table_hub_id`, `ix_pending_commands_hub_status_created`, `ix_sessions_user_expires`). Made `temp` and `humid` in `temperature_data` `nullable=True` to support partial node payloads. Enforced unique constraints `uq_*_dev_timestamp`. |
| **Phase 4** | High-Throughput Batch Ingestion | Built `POST /api/iot/batch` accepting up to 1000 items/batch. Replaced per-request hub heartbeat commits with an in-memory throttled `HubAuthCache` (30s window), resolving the CRIT-01 auth double-commit bug. Added deterministic UUID5 `data_id` generation, in-batch deduplication, and chunked upserts (500 items) with `bulk_insert_or_ignore` (`ON CONFLICT DO NOTHING`). Suppressed alert bursts by evaluating thresholds strictly on the newest point per device. |
| **Phase 5** | Presence Sweeper & N+1 Elimination | Decoupled device connectivity evaluation into a 15-second background task (`evaluate_device_presence_batch` in `app/services/presence.py`, detection lag $\le 75\text{s}$). Enforced a strict read-only invariant across `GET /api/devices`, `GET /api/rooms`, and `GET /api/rooms/{id}/map` (0 database writes). Replaced iterative N+1 queries with eager joins and indexed lookups. |
| **Phase 6** | Verification, Benchmarks & Zero-Lock SLA | Created 1,000,000 synthetic row benchmark generator (`tools/seed_benchmark_telemetry.py`) and an async concurrency stress testing tool (`tools/benchmark_concurrency_stress.py`). Executed comprehensive verification suite with 427 total passing tests (249 pytest + 178 Vitest across 22 suites). |

## 2. Root Cause Analysis: Telemetry & Query HTTP 500 Failures

During high-concurrency stress testing and production field operation, three primary failure modes caused HTTP 500 Internal Server Errors:

1. **Root Cause: Auth Double-Commit and SQLite Write Lock Collisions (CRIT-01)**
   - *Failure Mechanism*: `verify_hub_identity` dependency called `db.commit()` on every telemetry request to update `hub.last_seen`. When concurrent hubs posted telemetry or multiple dashboard readers polled the database, SQLite's single-writer architecture deadlocked. Requests exceeded the default 5-second busy timeout and raised `sqlite3.OperationalError: database is locked`, aborting requests with HTTP 500.
   - *Resolution*: Implemented `HubAuthCache` with thread-safe in-memory caching and 30-second heartbeat throttling. Heartbeat updates stage into session memory (`stage_hub_heartbeat`), and commit alongside telemetry in a single atomic transaction.
2. **Root Cause: Non-Nullable Schema Constraints on Partial Telemetry (HIGH-02)**
   - *Failure Mechanism*: In `temperature_data`, `temp` and `humid` columns were defined with `nullable=False`. When an ESP node reported disconnected sensor hardware (NaN values parsed to `None`) or custom nodes transmitted temperature-only payloads, SQLAlchemy raised `IntegrityError: NOT NULL constraint failed: temperature_data.temp`.
   - *Resolution*: Migration `c1a8b9f0e2d3` altered `temp` and `humid` to `nullable=True`. Ingestion logic now gracefully records partial telemetry without rollbacks.
3. **Root Cause: Ingestion Rollback on Duplicate WAL Replays**
   - *Failure Mechanism*: When replaying edge WAL queues after network reconnects, duplicate `(dev_id, timestamp)` records were submitted. Before unique indexes existed, `bulk_insert_or_ignore` failed on SQLite with `OperationalError: ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`.
   - *Resolution*: Added `uq_temp_dev_timestamp`, `uq_ats_dev_timestamp`, and `uq_data_dev_timestamp`. In `bulk_insert_or_ignore`, added a defensive fallback to `INSERT OR IGNORE` on `OperationalError`, and created an automatic startup migration (`init_sqlv5.migrate_indexes`) that prunes duplicate rows before unique index creation.

## 3. Production Incidents Resolved

- **CRIT-01 (Auth Double-Commit Lock Starvation)**: Resolved via `HubAuthCache` and atomic single-transaction commit.
- **HIGH-01 (History Query 500 & Memory Exhaustion)**: Resolved via Downsampling V2, SARGable indexes, and sub-1000 bypass.
- **HIGH-02 (Partial Payload Ingestion Crash)**: Resolved via `nullable=True` migration and defensive payload normalization.
- **HIGH-03 (Offline WAL Replay Alert Storm)**: Resolved by evaluating alerts strictly once per device on its newest reading in `POST /api/iot/batch`.
- **HIGH-04 (Read-Time Presence Lock Contention)**: Resolved by moving presence evaluation to an isolated 15-second background sweeper and enforcing read-only query invariants.

## 4. Measured Benchmark Invariants (Baseline)

Benchmarked against a 1,000,000-row dataset across 30 days under concurrent ingestion writers (single and 75-point batch) and dashboard readers (30-day downsampling, room maps, device lists, alerts):

| Invariant ID | Assertion Description | Measured Value (SQLite WAL) | Target SLA | Status |
|---|---|---|---|---|
| `inv1_downsample_p95` | 30d History Downsample P95 Latency | 891.28ms | < 1000.0ms (SQLite) / < 300.0ms (PG) | **PASS** |
| `inv2_single_write_p95` | POST /api/iot Single-Write P95 Latency | 173.89ms | < 200.0ms | **PASS** |
| `inv2_single_write_p99` | POST /api/iot Single-Write P99 Latency | 187.50ms | < 500.0ms | **PASS** |
| `inv3_batch_write_p95` | POST /api/iot/batch Batch-Write P95 Latency | 302.99ms | < 350.0ms | **PASS** |
| `inv3_batch_write_p99` | POST /api/iot/batch Batch-Write P99 Latency | 388.17ms | < 750.0ms | **PASS** |
| `inv4_ingestion_throughput` | Ingestion Pipeline Throughput | 583.5 pts/sec | > 500.0 pts/sec | **PASS** |
| `inv5_zero_database_locked_errors` | Database Locked (`database is locked`) Count | 0 | == 0 | **PASS** |
| `inv5_zero_timeout_errors` | Timeout / Connection Drops Count | 0 | == 0 | **PASS** |
| `inv5_zero_http_500_errors` | HTTP 500 Internal Server Errors Count | 0 | == 0 | **PASS** |

Codified in automated pytest suites (historical baseline raw data archived in git history).

