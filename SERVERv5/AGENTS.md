# AGENTS.md — SERVERv5 (HubGate V5 Cloud Gateway)

FastAPI + Pydantic v2 + SQLAlchemy 2 ingestion gateway for IoT telemetry (the "cloud" side). Code lives in `SERVERv5/v5/`. All doc text is Indonesian-English hybrid matching the codebase's existing READMEs.

## Ownership

- **SERVERv5/**: cloud gateway source — FastAPI app, auth/RBAC, DB models, migrations, tests, deploy scripts
- Owned by root AGENTS.md for repo-wide rules and the DOX framework

## Commands (run from `SERVERv5/v5/` with venv active)

| Command | What it does |
|---|---|
| `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (Linux) | Activate virtualenv |
| `uvicorn hubgatev5:api --host 127.0.0.1 --port 8000` | Run dev server (prod: behind Nginx HTTPS on 443) |
| `python init_sqlv5.py` | Create/migrate tables + seed default hub |
| `python create_admin_user.py` | Create/update a User (admin/operator/viewer) |
| `python backfillv5.py` | Migrate legacy `data_table` rows into `temperature_data`/`ats_data` |
| `python -m pytest test_*.py` | Run tests (SQLite-based, no PostgreSQL needed) |
| `bash run_hubgatev5.sh` (Linux) | Full deploy: SSL cert + Nginx config + venv + uvicorn |
| `bash CheckSec.sh` (Linux) | Local security audit (UFW, file permissions) |

## Stack

Python 3.14 (venv), FastAPI, Uvicorn, Pydantic v2 (discriminated unions), SQLAlchemy 2.0, PostgreSQL (production) with **SQLite fallback** (`DATABASE_URL` unset), slowapi rate limiting, argon2-cffi password hashing, psycopg2-binary. `requirements.txt` in `v5/`.

## Architecture

- Entry: `hubgatev5.py` exports `api` (FastAPI app) — module name is `hubgatev5`, not `main`.
- Tables (`modelsv5.py`): `hub_table`, `rooms`, `dev_table` (with `last_seen`, `last_status`, `marker_x`, `marker_y`), `device_threshold_config`, `data_table`, `event_log`, `temperature_data`, `ats_data`, `pending_commands`, `users`, `sessions`, `login_attempts`
- Payload validation (`schemasv5.py`): `IotPayload` = discriminated union on `DEV_TYPE` (`ATSData`, `TSData`, `ACCData`, `ACData`, `PUMPData`); `ATSCommand` and `ACCommand` validated for mode/power/temperature actions.
- Auth (`auth.py` + `schemas_auth.py`): Argon2id hashing, timing-safe dummy-hash verification, sessions (2h sliding / 12h absolute cap), per-username lockout (5 fails → 15 min → 423 Locked), cookie `session_id` (httponly, secure, samesite=lax).
- Alert Engine & Presence: Synchronous threshold evaluation in `receive_iot` for temperature (warning/critical, debounce window, hysteresis recovery) and ATS emergency state. Automatic presence state tracking (`last_seen`, `last_status`), with 25s timeout `DEVICE_OFFLINE` generation and `DEVICE_ONLINE` recovery resolution.

## Endpoints

| Endpoint | Auth | Rate limit | Purpose |
|---|---|---|---|
| `POST /api/admin/hubs` | `require_role("admin")` | 10/min | Register a new Hub |
| `GET /api/hubs` | authenticated user | 60/min | List hubs with grouped devices; online = `last_seen` within 25s |
| `POST /api/hubs/pair` | `X-Hub-Key` header | 10/min | Known+active hub → refresh heartbeat, `{status:"paired"}`; unknown hub + matching `HUB_BOOTSTRAP_KEY` env (timing-safe) → 202 `{status:"pending_approval"}` row created `is_active=False`; known inactive → 401 |
| `POST /api/hubs/{id}/approve` | `require_role("admin")` | 30/min | Approve pending hub (`is_active=True`) |
| `POST /api/hubs/{id}/revoke` | `require_role("admin")` | 30/min | Revoke hub (`is_active=False`, rejected by hub auth thereafter) |
| `GET /api/rooms` | authenticated user | 60/min | List all rooms with device counts & floor plan URL |
| `POST /api/rooms` | `require_role("admin")` | 30/min | Create a new room |
| `PATCH /api/rooms/{id}` | `require_role("admin")` | 30/min | Update room name, hub assignment, or floor plan |
| `DELETE /api/rooms/{id}` | `require_role("admin")` | 30/min | Delete room (rejects if devices assigned) |
| `POST /api/gateways/{id}/room` | `require_role("admin")` | 30/min | Associate a gateway with a room |
| `POST /api/rooms/{id}/floor-plan` | `require_role("admin")` | 30/min | Upload floor plan image (PNG/JPEG/WebP/SVG, max 5MB) |
| `GET /api/rooms/{id}/map` | authenticated user | 60/min | Room map with floor plan URL and device markers |
| `GET /api/devices` | hub headers OR user session | 60/min | Whitelist sync for hubs OR device list with `?status=pending/active/all` |
| `POST /api/devices/{id}/approve` | `require_role("admin")` | 30/min | Approve pending device |
| `POST /api/devices/{id}/pair` | `require_role("admin")` | 30/min | Pair pending device (name, room, marker, thresholds) |
| `POST /api/devices/{id}/unpair` | `require_role("admin")` | 30/min | Unpair device (clears room/marker, deactivates) |
| `PUT /api/devices/{id}/thresholds` | `require_role("admin")` | 30/min | Update warning/critical/hysteresis/debounce thresholds |
| `GET /api/devices/{id}/history` | authenticated user | 60/min | Historical telemetry time-series (`?range=6h,24h,7d,30d,all`). **Downsampling**: fetch latest-first (DESC,LIMIT) for ≤1000 rows, else bucket-average into ~1000 time buckets (SQLite `strftime` / Postgres `extract epoch`) so dense windows (ATS ~1.5 Hz = 11 min per 1000 rows) now span the full window |
| `GET /api/alerts` | authenticated user | 60/min | Filterable alerts list (rooms, devices, severity, status, times) |
| `POST /api/iot/unapproved` | hub headers | 60/min | Report unknown MAC blocked at edge |
| `POST /api/iot` | hub headers | 120/min | Receive telemetry (TS/ATS/AC) and evaluate thresholds |
| `POST /api/devices/{id}/command` | session (RBAC per action) | 30/min | Queue command; `reset`=admin only, others=admin/operator |
| `GET /api/hub/commands` | hub headers | 30/min | Hub polls pending commands |
| `POST /api/hub/commands/{id}/delivered` | hub headers | 30/min | Ack command delivery |
| `POST /api/auth/login` / `logout` / `me` | — / cookie / cookie | 5/min | Auth session endpoints |

## Test Files (SQLite)

- `test_models_migration.py` — additive schema migrations & models
- `test_milestone1.py` — core ingest + tables
- `test_milestone2_3.py` — telemetry/command flows
- `test_rooms_pairing.py` — rooms CRUD, gateway association, device pair/unpair
- `test_floor_plan_map.py` — floor plan upload & map marker endpoints
- `test_alert_evaluation.py` — alert engine debounce, hysteresis, and query filters
- `test_device_history.py` — historical telemetry time-series querying
- `test_milestone_auth.py`, `test_auth_milestone3a.py`, `test_auth_endpoints_milestone4a.py` — auth/RBAC/lockout
- Tests set `DATABASE_URL=sqlite:///./test_*.db` and delete the db at start; `.db` files are generated artifacts

## Non-Obvious Facts

- Rate limiter keys on `X-Real-IP`/`X-Forwarded-For` (not `get_remote_address`) — see `get_forwarded_address`
- `JSONB().with_variant(JSON, "sqlite")` keeps production Postgres and test SQLite compatible
- `init_sqlv5.py` auto-migrates `dev_table.hub_name` → `hub_id` + FK and additive columns (`room_id`, `marker_x`, `marker_y`, `event_log` fields)
- `auth.py` generates a dummy Argon2 hash at import time for timing-safe user-missing checks
- `send_device_command` does RBAC by payload key (`reset` present) before Pydantic validation
- `cert.crt` is auto-generated by the deploy script (self-signed); `cert.key` must stay chmod 600
- `.env` holds secrets (`DATABASE_URL`, `SERVER_USER`, `PASSWORD_USER`, `HUB_NAME`, `HUB_KEY`) — never commit
- Physical nodes (e.g. `80:7D:3A:5E:3D:DB`) require registration/pairing in `dev_table` before HubBrain forwards telemetry to `/api/iot`
- `HUB_BOOTSTRAP_KEY` env (optional): when set, unknown hubs presenting it via `/api/hubs/pair` self-register as pending approval; unset disables open bootstrap entirely. Bootstrap key becomes the new hub's stored credential — rotate per-hub after approval
- `hub_table` gained additive columns `last_seen` (tz-aware, stamped on every successful hub-auth request) and `status` (`online`/`offline`, derived from a 25s cutoff in `GET /api/hubs`)
- Ops: the VPS also runs **chrony as an NTP server** for campus IoT hubs (`allow 10.33.0.0/16`, UFW `123/udp` from campus ranges) — edge Pis have no internet and sync time from this VPS

## Work Guidance

- Keep discriminated-union pattern in `schemasv5.py` when adding new device types (see README §6)
- Verify `model_validator` context usage (`ValidationInfo`) for validations needing DB access
- New endpoints: add limiter decorator + auth dependency; match existing style (Indonesian comments)
- Keep tests green: `python -m pytest` from `v5/` — no PostgreSQL required

## Verification

- `python -m pytest test_*.py` (from `SERVERv5/v5/`, venv active)
- `python init_sqlv5.py` after model changes (idempotent + auto-migration)

