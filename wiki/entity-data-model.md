---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-downsampling-v2.md, wiki/concept-alert-engine.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/modelsv5.py, server/init_sqlv5.py, server/alembic/versions/c1a8b9f0e2d3_schema_indexing_and_nullability.py, server/AGENTS.md, commit:8f8f6cd, commit:9961f5c]
updated: 2026-09-02
---

# HubGate V5 Data Model

All ORM entities live in `server/modelsv5.py`. The database architecture targets **PostgreSQL 16** for high-concurrency production deployments (multi-writer MVCC with connection pooling) and **SQLite 3 WAL mode** for local edge and development nodes (`hubgatev5.db`, ~430MB).

## Table Inventory & Primary Schema

- `hub_table`: Registered edge gateways connecting physical facilities to HubGate.
  - Columns: `hub_id` (PK, String), `hub_name` (String, nullable=False), `hub_key` (String, nullable=False), `room` (String, nullable=True), `is_active` (Boolean, default=True), `created_at` (UTC datetime), `last_seen` (UTC datetime, nullable), `status` (String, default="offline").
- `rooms`: Physical facility spaces mapped to floor plans.
  - Columns: `id` (PK, String), `name` (String, unique, nullable=False), `hub_id` (FK `hub_table.hub_id`, nullable), `floor_plan_image_path` (String, nullable), `created_at` (UTC datetime).
- `temperature_data`: High-volume typed environmental readings (temperature and humidity) from TS and AC sensors.
  - Columns: `data_id` (PK, deterministic UUID), `dev_id` (FK `dev_table.dev_id`, `nullable=False`), `timestamp` (UTC datetime, `nullable=False`), `temp` (Float, `nullable=True`), `humid` (Float, `nullable=True`).
  - Indexing: Composite index `idx_temp_dev_timestamp(dev_id, timestamp DESC)` for fast history scanning.
  - Constraints: `UniqueConstraint("dev_id", "timestamp", name="uq_temp_dev_timestamp")` for ingestion idempotency.
- `ats_data`: High-volume typed electrical readings from Automatic Transfer Switch controllers.
  - Columns: `data_id` (PK, deterministic UUID), `dev_id` (FK `dev_table.dev_id`, `nullable=False`), `timestamp` (UTC datetime, `nullable=False`), `state` (String), `pln` (Float), `genset` (Float), `aki` (Float starter battery DC), `rem_hour`, `rem_min`, `rem_sec`, `auto_mode` (Boolean), `emergency` (Boolean).
  - Indexing: Composite index `idx_ats_dev_timestamp(dev_id, timestamp DESC)`.
  - Constraints: `UniqueConstraint("dev_id", "timestamp", name="uq_ats_dev_timestamp")`.
- `data_table`: Legacy raw-JSON telemetry ingest path.
  - Columns: `data_id` (PK), `dev_id` (FK `dev_table.dev_id`), `dev_name`, `timestamp` (UTC datetime), `payload` (JSON).
  - Indexing: `ix_data_table_dev_ts_desc(dev_id, timestamp DESC)`.
  - Constraints: `UniqueConstraint("dev_id", "timestamp", name="uq_data_dev_timestamp")`.
- `dev_table`: Hardware inventory registering paired IoT nodes.
  - Columns: `dev_id` (PK), `dev_name`, `dev_type` (`TS`, `ATS`, `AC`), `hub_id` (FK `hub_table.hub_id`), `room_id` (FK `rooms.id`), `marker_x`, `marker_y`, `is_active` (Boolean), `last_seen` (UTC datetime), `last_status` (`online`/`offline`).
  - Indexing: `ix_dev_table_hub_id`, `ix_dev_table_room_id`, `ix_dev_table_dev_name`.
- `device_threshold_config`: Per-device warning and critical thresholds for alert evaluation.
  - Columns: `dev_id` (PK / FK `dev_table.dev_id`), `warning`, `critical`, `hysteresis` (default 0.5°C / 0.2V), `debounce_seconds` (default 60s).
- `event_log`: Alerts and system event log.
  - Columns: `event_id` (PK), `alarm`, `timestamp` (UTC datetime), `message`, `dev_id`, `room_id`, `metric`, `severity`, `value`, `threshold`, `resolved_at` (UTC datetime, nullable).
  - Indexing: `ix_event_log_dev_metric_ts(dev_id, metric, timestamp DESC)`, `ix_event_log_room_ts(room_id, timestamp DESC)`, `ix_event_log_dev_resolved(dev_id, resolved_at)`, `ix_event_log_ts_desc(timestamp DESC)`.
- `pending_commands`: Downlink queue for edge hub dispatch.
  - Columns: `command_id` (PK), `dev_id` (FK `dev_table.dev_id`), `hub_id` (FK `hub_table.hub_id`), `payload` (JSON), `status` (`pending`/`delivered`), `created_at` (UTC datetime), `delivered_at` (UTC datetime, nullable).
  - Indexing: `ix_pending_commands_hub_status_created(hub_id, status, created_at)`.
- `schedules`: Automated cron job dispatch for device actions (e.g. ATS warmup).
  - Columns: `id` (PK, UUID String), `dev_id` (FK `dev_table.dev_id`, `nullable=False`), `hub_id` (FK `hub_table.hub_id`, nullable), `cron_expr` (String(64), nullable=False), `payload` (JSON, nullable=False), `tz` (String(32), default `Asia/Jakarta`), `enabled` (Boolean, default True), `created_by` (String, nullable=False), `created_at` (UTC datetime), `updated_at` (UTC datetime), `next_run_at` (UTC datetime, nullable).
  - Indexing: `ix_schedules_enabled_hub(enabled, hub_id)`, `ix_schedules_dev(dev_id)`.
- `users`, `sessions`, `login_attempts`: Argon2id credential store, active user sessions (indexed by `ix_sessions_user_expires(user_id, expires_at)`), and brute-force lockout tracking.

## Alembic Migration `c1a8b9f0e2d3` & Schema Hardening

Schema enhancements implemented in migration `c1a8b9f0e2d3` (Phase 3 backend hardening) addressed critical operational bottlenecks:

1. **Partial Payload Nullability (`nullable=True`)**:
   In `temperature_data`, columns `temp` and `humid` were converted to `nullable=True`. Previously, sensors reporting partial payloads (e.g. humidity sensor disconnects, or AC controllers publishing only power states) caused unhandled `IntegrityError` exceptions, rolling back the transaction and failing ingest with HTTP 500.
2. **SARGable Composite Indexing**:
   Replaced table-wide linear scans with B-tree composite indexes matching exact query patterns. Range scans on `dev_id` and `timestamp` now execute in logarithmic time, enabling 30-day downsampling across 1,000,000 rows to complete in < 300ms on PostgreSQL and < 1000ms on SQLite.
3. **Unique Constraints (`uq_*_dev_timestamp`)**:
   Enforces `(dev_id, timestamp)` uniqueness across `temperature_data`, `ats_data`, and `data_table`. These constraints back the `ON CONFLICT (dev_id, timestamp) DO NOTHING` clause in `bulk_insert_or_ignore`, enabling safe, idempotent replays of buffered edge WAL telemetry. Startup routines in `server/init_sqlv5.py` and `server/app/services/scheduler.py` automatically prune duplicate historical tuples before index creation on SQLite edge instances.
4. **Non-Nullable Foreign Key Constraints**:
   Guarantees referential integrity on `temperature_data.dev_id`, `ats_data.dev_id`, `pending_commands.dev_id`, and `pending_commands.hub_id`. Deleting a hub cleanly cascades or nulls associated entity references.

