---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-alert-engine.md]
sources: [server/modelsv5.py, server/alembic/versions/, server/AGENTS.md]
updated: 2026-08-31
---

# HubGate V5 data model

All tables live in `server/modelsv5.py`. The database architecture targets **PostgreSQL 16** for high-concurrency production deployments (multi-writer MVCC with connection pooling) and **SQLite 3 WAL mode** for local edge/dev nodes (`/opt/smsb/SERVERv5/v5/hubgatev5.db`, ~430MB).

Tables:
- `data_table`: Legacy raw-JSON ingest path.
- `temperature_data`: Typed temperature & humidity telemetry with composite index `idx_temp_dev_timestamp(dev_id, timestamp.desc())`.
- `ats_data`: Typed ATS electrical telemetry with composite index `idx_ats_dev_timestamp(dev_id, timestamp.desc())`.
- `dev_table`: Device inventory with foreign key `hub_id` indexed by `ix_dev_table_hub_id`.
- `rooms`: Building rooms with floor plan metadata.
- `event_log`: Alerts and system events indexed by `ix_event_log_dev_metric_ts(dev_id, metric, timestamp.desc())`.
- `pending_commands`: Edge downlink command queue indexed by `ix_pending_commands_hub_status_created(hub_id, status, created_at)`.
- `schedules`: Flexible cron warmup jobs (`cron_expr`, `payload` JSON, `tz` Asia/Jakarta, `enabled`, `next_run_at`).
- `users`, `sessions`, `login_attempts`: Argon2id auth and session management.

Key relationships & invariants:
- `dev_table.hub_id` → `hub_table` (a hub's whitelist is its active devices).
- `rooms.hub_id` → `hub_table` (nullable — deleting a hub nulls room links).
- SARGable index optimization ensures single-pass downsampling aggregation over 1,000,000 rows executes in < 300ms on PostgreSQL (and < 1000ms on SQLite).
- Timestamps are stored in UTC. On SQLite they round-trip naive and the API re-attaches UTC via the `UtcDateTime` validator before serialization (see [concept-time-conventions.md](concept-time-conventions.md)).
