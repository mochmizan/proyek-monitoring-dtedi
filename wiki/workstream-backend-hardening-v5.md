---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-downsampling-v2.md, wiki/concept-telemetry-pipeline.md]
sources: [server/databasev5.py, server/app/routers/devices.py, server/app/routers/iot.py, server/app/routers/rooms.py, server/app/services/presence.py, tools/benchmark_concurrency_stress.py, tools/seed_benchmark_telemetry.py]
updated: 2026-09-02
---

# Workstream: HubGate V5 Backend Hardening

Completed multi-phase architectural hardening of the HubGate V5 backend to ensure rock-solid high concurrency, sub-second query performance over 30-day telemetry spans, bounded memory usage, and zero database locked contention.

## Phase Architecture Summary

| Phase | Focus Area | Key Implementations |
|---|---|---|
| Phase 1 | Database Engine Hardening | Connection pool bounding on PostgreSQL (pool_size=10, max_overflow=5, 15s statement_timeout). SQLite WAL connect-time PRAGMAs: journal_mode=WAL, busy_timeout=10000, synchronous=NORMAL, foreign_keys=ON, cache_size=-64000, mmap_size=268435456. |
| Phase 2 | Downsampling Query Plan & Aggregation V2 | Single-pass mathematical epoch bucketing. func.unixepoch(col) in SQLite 3.38+ for 2x timestamp parsing speedup. Single-pass min/max envelopes for temperature, humidity, PLN, genset, and battery voltage. Exact bounds total_points <= max_points. |
| Phase 3 | Schema Hardening & SARGable Indexes | Composite indexes created: ix_event_log_dev_metric_ts, ix_dev_table_hub_id, ix_pending_commands_hub_status_created, idx_temp_dev_timestamp, idx_ats_dev_timestamp. Clean Alembic migrations and nullable constraint fixes. |
| Phase 4 | High-Throughput Ingestion & Batching | POST /api/iot/batch endpoint supporting up to 100 items/batch. Deterministic data_id = sha256(dev_id:timestamp_iso)[:16]. Dialect-specific idempotency via bulk_insert_or_ignore (ON CONFLICT DO NOTHING in PostgreSQL, INSERT OR IGNORE in SQLite). Deduplicated alert/presence evaluation on the latest item per device. |
| Phase 5 | Presence Worker & N+1 Elimination | 5s background presence sweeper (sweep_presence_loop) decoupled from read requests. Enforced read-only invariant: GET /api/devices, GET /api/rooms, GET /api/rooms/{id}/map execute 0 database writes. N+1 queries eliminated: list_rooms uses single SQL outer join; get_room_map uses joinedload and window functions (<= 4 queries total). |
| Phase 6 | Verification & Benchmarking | 1,000,000 synthetic row benchmark seeder (tools/seed_benchmark_telemetry.py). Async-native high-concurrency stress testing utility (tools/benchmark_concurrency_stress.py). Automated verification test suite (server/test_phase6_verification_benchmark.py). All 177 server tests passing 100%. |

## Measured Benchmark Invariants (Baseline)

Measured against 1,000,000 historical rows seeded across 30 days under concurrent ingestion writers, dashboard polling readers, and heavy 30-day downsampling readers:

| Invariant | Description | Measured (SQLite WAL) | Target SLA | Status |
|---|---|---|---|---|
| Inv 1 | 30d History Downsample P95 | 891.28ms | < 1000.0ms (SQLite) / < 300.0ms (PG) | **PASS** |
| Inv 2 | POST /api/iot Single-Write P95 | 173.89ms | < 200.0ms | **PASS** |
| Inv 2 | POST /api/iot Single-Write P99 | 187.50ms | < 500.0ms | **PASS** |
| Inv 3 | POST /api/iot/batch Batch-Write P95 | 302.99ms | < 350.0ms | **PASS** |
| Inv 3 | POST /api/iot/batch Batch-Write P99 | 388.17ms | < 750.0ms | **PASS** |
| Inv 4 | Ingestion Pipeline Throughput | 583.5 pts/sec | > 500.0 pts/sec | **PASS** |
| Inv 5 | Database Locked Errors | 0 | == 0 | **PASS** |
| Inv 5 | Timeout / Dropped Connections | 0 | == 0 | **PASS** |
| Inv 5 | HTTP 500 Internal Server Errors | 0 | == 0 | **PASS** |
