---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-alert-engine.md]
sources: [server/modelsv5.py, server/alembic/versions/, server/AGENTS.md]
updated: 2026-08-31
---

# HubGate V5 data model

All tables live in `server/modelsv5.py`; prod is a single SQLite file (`/opt/smsb/SERVERv5/v5/hubgatev5.db`, ~430MB, smsb-owned) — `data_table` is the legacy raw-JSON ingest path; `temperature_data` and `ats_data` are the typed telemetry tables; `event_log` records threshold/emergency/offline alerts with `resolved_at`; `pending_commands` queues downlink commands for hubs; `schedules` (alembic `b7c9e2f1a4d8`) stores flexible cron warmup jobs (`cron_expr`, `payload` JSON, `tz` Asia/Jakarta, `enabled`, `next_run_at`); `users`/`sessions`/`login_attempts` back the Argon2id auth.

Key relationships: `dev_table.hub_id` → `hub_table` (a hub's whitelist is its active devices); `rooms.hub_id` → `hub_table` (nullable — deleting a hub nulls room links); `event_log.dev_id`/`room_id` denormalized for filter queries; telemetry rows are append-only per device and downsampled on read (~1000 AVG buckets per history window).

Timestamps are stored UTC. On SQLite they round-trip naive; the API re-attaches UTC via the UtcDateTime validator before serialization (see [concept-time-conventions.md](concept-time-conventions.md)).
