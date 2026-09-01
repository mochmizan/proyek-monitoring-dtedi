# AGENTS.md — server (HubGate V5)

## Purpose

FastAPI cloud gateway (HubGate V5) — ingestion, auth/RBAC, rooms/devices/alerts API, and telemetry pipeline for IoT fleet. Code lives in `server/`.

## Ownership

- **server/** owns HubGate V5: FastAPI app, DB models/migrations, auth, services, and gateway API.
- Owned by root AGENTS.md for repo-wide DOX and global rules.

## Local Contracts

### Stack

Python 3.14, FastAPI 0.136.1, Uvicorn 0.46.0, Pydantic 2.13.3, SQLAlchemy 2.0.49, Alembic, PostgreSQL (prod) + SQLite fallback (`DATABASE_URL` unset), SlowAPI 0.1.10, argon2-cffi 25.1.0, psycopg2-binary 2.9.12, python-multipart 0.0.27, APScheduler 3.10.4 + tzdata (Asia/Jakarta) — all pinned `==` in `requirements.txt`.

### Entry & Architecture

- Entry: `hubgatev5.py` shim re-exports `api` from `app/main.py`; run via `uvicorn hubgatev5:api --host 127.0.0.1 --port 8000` (prod behind Nginx 443). Canonical assembly at `app/main.py` (CORS, rate limiter, scheduler `lifespan`, `GET /health` + `/api/health` unauthenticated DB `SELECT 1` check, static mount).
- Routers: `app/routers/` — `auth`, `hubs`, `rooms`, `devices` (`GET /api/devices/{dev_id}` single-device detail with computed status & thresholds), `alerts`, `iot`, `commands` (`GET /api/commands/{command_id}` delivery status check), `schedules`.
- Core: `app/core/config`, `app/core/rate_limit`, `app/core/logging`.
- Services: `app/services/alert_engine`, `app/services/presence`, `app/services/scheduler` (APScheduler `BackgroundScheduler` `Asia/Jakarta` cron → `pending_commands`).
- DB: `app/modelsv5.py`; Alembic at `alembic/` (`alembic.ini` + `versions/04a48dbce60b_initial_schema_as_observed.py` + `b7c9e2f1a4d8_add_schedules.py`); `init_sqlv5.py` is idempotent additive migration for fallback.

### Tables

`hub_table`, `rooms`, `dev_table` (`last_seen`, `last_status`, `marker_x`, `marker_y`, `hub_id` FK), `device_threshold_config`, `data_table`, `event_log`, `temperature_data`, `ats_data`, `pending_commands`, `schedules` (`cron_expr`, `payload` JSON, `tz` `Asia/Jakarta`, `enabled`, `next_run_at`), `users`, `sessions`, `login_attempts`.

### Datetime Contract

Outgoing datetimes are tz-aware UTC via `UtcDateTime/OptionalUtcDateTime` (`AfterValidator` attaches UTC to naive SQLite values) in `schemasv5.py` - JSON carries `Z` so browsers never double-shift (alerts `new Date` bug 2026-08-31). Apply the types to any new response-model datetime field. Prod runtime = legacy path `/opt/smsb/SERVERv5/v5` kept fresh by the deploy-hook rsync (see `deploy/AGENTS.md`).

### Payload Validation & Schemas

`app/schemasv5.py`: `IotPayload` is discriminated union on `DEV_TYPE` (`ATSData`, `TSData`, `ACCData`, `ACData`, `PUMPData`); `IotDataBase` uses `extra="allow"` + optional `HUB_TS` (alias `_hub_created_at`) so hub WAL-replay epoch passes through without 422; `ATSCommand`/`ACCommand` validated for mode/power/temperature actions; `CommandStatusResponse` models `command_id`, `dev_id`, `hub_id`, `payload`, `status`, `created_at: OptionalUtcDateTime`, `delivered_at: OptionalUtcDateTime`; `DeviceResponse` models full device metadata with `ThresholdConfigSchema` and computed `status` (`online`/`offline`/`pending`).

### Auth

Argon2id hashing with dummy-hash timing-safe check, sessions (2h sliding / 12h absolute cap), per-username lockout (5 fails → 15 min → 423 Locked), cookie `session_id` (`httponly`/`secure`/`samesite=lax`). Hub auth via `X-Hub-Key`; bootstrap via `HUB_BOOTSTRAP_KEY` env (timing-safe, creates `is_active=False` pending hub).

### Rate Limit & Health & History & Commands

- Rate limit keys on `X-Real-IP` / `X-Forwarded-For` `parts[0]` via `get_forwarded_address` (not `get_remote_address`).
- `GET /health` and `GET /api/health` unauthenticated, return `{"status":"ok","db":"up"|"down"}`.
- History `GET /api/devices/{id}/history` (`?range=6h,24h,7d,30d,all`) downsamples to ~1000 buckets via AVG (`strftime` on SQLite / `extract epoch` on Postgres); ≤1000 rows returned latest-first without bucketing.
- Single device detail `GET /api/devices/{dev_id}` returns `DeviceResponse` with 25s presence status and threshold config.
- Command status check `GET /api/commands/{command_id}` returns `CommandStatusResponse` with UTC `created_at` and `delivered_at`.

### Alert Engine & Presence

Synchronous threshold evaluation in `receive_iot` (temperature warning/critical overtemperature and ATS starter battery undervoltage: `BATTERY_WARNING` 11.8V / `BATTERY_CRITICAL` 11.2V with recovery at $V \ge \text{warning} + \text{hysteresis}$, debounce window, hysteresis recovery) and ATS emergency. Telemetry timestamps use `event_time` = hub `_hub_created_at`/`HUB_TS` epoch (offline WAL replay preserves capture time) else `now_utc` (UTC). `alert_engine` auto-resolves open `ATS_EMERGENCY` and suppresses new ones when payload reports `EMERGENCY=1` but `PLN>210 && GENSET<80` (case-insensitive keys; stuck-latch suppression for genset-disconnected field units). Presence tracks `last_seen`/`last_status`; `DEVICE_OFFLINE` after 25s timeout, `DEVICE_ONLINE` on recovery; `GET /api/hubs` derives `status` (`online`/`offline`) from 25s cutoff and stamps `hub_table.last_seen`.

## Work Guidance

- New device types: extend discriminated union in `schemasv5.py` (`DEV_TYPE` literal + new model), keep `model_validator` + `ValidationInfo` pattern for DB-aware validation.
- New endpoints: add SlowAPI `limiter` decorator + auth dependency (`require_role` or hub header); follow existing Indonesian-comment style.
- Keep `JSONB().with_variant(JSON, "sqlite")` for Postgres/SQLite compat.
- Keep tests green (SQLite, no Postgres needed).

## Verification

- `python -m pytest test_*.py` from `server/` (venv active) — SQLite-based.
- `python init_sqlv5.py` after model changes (idempotent + auto-migrates `dev_table.hub_name` → `hub_id` FK and additive columns).
- `docker compose config` binds `127.0.0.1:5432/1883` (not `0.0.0.0`).

## Child DOX Index

| Path | Scope |
|---|---|
| — | No child DOX; `server/` is a leaf. |
