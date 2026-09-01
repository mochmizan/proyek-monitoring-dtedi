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

Telemetry lands at `POST /api/iot` as a Pydantic discriminated union on `DEV_TYPE` (ATSData/TSData/ACCData/ACData). Row timestamps use `event_time` = hub `_hub_created_at` epoch when replayed from an offline WAL, else server `now_utc`. History (`GET /api/devices/{id}/history`) downsamples to ~1000 AVG buckets per range window.

In production it runs from the legacy path `/opt/smsb/SERVERv5/v5` (see [entity-deploy-pipeline.md](entity-deploy-pipeline.md)) against a ~430MB SQLite database; PostgreSQL is used via docker compose in dev with SQLite fallback. Outgoing datetimes follow the UtcDateTime contract ([concept-time-conventions.md](concept-time-conventions.md)).

Hubs can be hard-deleted by admins via `DELETE /api/hubs/{hub_id}` (409 while devices are paired; room links nulled) — added 2026-08-31 to remove seeded dummy hubs.
