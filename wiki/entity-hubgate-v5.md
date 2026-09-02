---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-data-model.md, wiki/entity-hubbrain-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-command-path.md, wiki/concept-alert-engine.md, wiki/entity-deploy-pipeline.md, wiki/concept-time-conventions.md]
sources: [server/app/main.py, server/app/routers/devices.py, server/app/routers/commands.py, server/schemasv5.py, server/AGENTS.md, commit:35708e4]
updated: 2026-09-01
---

# HubGate V5 (server/)

HubGate V5 is the FastAPI cloud gateway of the smsb stack, living in `server/`. It terminates telemetry ingestion from every edge hub, serves the dashboard API (rooms, devices, alerts, schedules, commands), and owns authentication and RBAC.

Assembly lives in `server/app/main.py` (the `hubgatev5.py` at the package root is a shim re-exporting `api`). Routers split by domain: `auth`, `hubs`, `rooms`, `devices`, `alerts`, `iot`, `commands`, `schedules`. Services hold the logic: `alert_engine` (threshold + ATS emergency evaluation on ingest), `presence` (25s offline detection), `scheduler` (APScheduler BackgroundScheduler, Asia/Jakarta).

Authentication is Argon2id with 2h sliding / 12h absolute sessions in httpOnly cookies; hubs authenticate per-request via `X-Hub-ID`/`X-Hub-Key` headers. Rate limiting is SlowAPI keyed on `X-Real-IP`/`X-Forwarded-For` first part. `GET /health` and `/api/health` are unauthenticated DB liveness checks.

Device management endpoints include list `GET /api/devices` and single-entity `GET /api/devices/{dev_id}` (returning `DeviceResponse` with presence derivation and attached `threshold_config`). Command dispatch endpoints include `POST /api/devices/{dev_id}/command` and status verification `GET /api/commands/{command_id}` (returning `CommandStatusResponse` with UTC `created_at` and `delivered_at` timestamps).

Telemetry lands at `POST /api/iot` (single item) or `POST /api/iot/batch` (up to 100 items/batch via `IotBatchRequest`) as a Pydantic discriminated union on `DEV_TYPE`. Bulk upserts use dialect-specific idempotency (`bulk_insert_or_ignore` using `ON CONFLICT DO NOTHING` on PostgreSQL and `INSERT OR IGNORE` on SQLite) keyed on deterministic `data_id = sha256(dev_id:timestamp_iso)[:16]`. In batch ingestion, alert rules and presence updates are evaluated once on the newest point per device.

Device history (`GET /api/devices/{id}/history`) utilizes [concept-downsampling-v2.md](concept-downsampling-v2.md) — single-pass mathematical epoch bucketing (`unixepoch` on SQLite 3.38+, `extract(epoch)` on PostgreSQL) computing average and exact min/max envelopes for temperature, humidity, PLN, genset, and battery voltage. Queries are bounded strictly to `max_points` (default 1000) and execute in < 300ms on PostgreSQL prod.

Presence is handled by a dedicated 5s background sweeper thread (`app/services/presence.py`), freeing all read endpoints (`GET /api/devices`, `GET /api/rooms`, `GET /api/rooms/{id}/map`) from database writes. `list_rooms` uses a single SQL outer join and `get_room_map` uses `joinedload` with window functions, executing <= 4 SQL queries total.

In production, HubGate targets **PostgreSQL 16** (hosted on VPS 10.33.102.172 / 100.108.98.30) with connection pool bounds (`pool_size=10, max_overflow=5`) and 15s statement timeout, while supporting SQLite 3 WAL mode for local edge nodes. Outgoing datetimes follow the UtcDateTime contract ([concept-time-conventions.md](concept-time-conventions.md)).

Hubs can be hard-deleted by admins via `DELETE /api/hubs/{hub_id}` (409 while devices are paired; room links nulled) — added 2026-08-31 to remove seeded dummy hubs.
