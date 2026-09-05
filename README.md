# SMSB â€” Smart Building Monitoring System

IoT monitoring & control platform for building infrastructure: temperature/humidity sensing, AC (IR) control, and ATS (Automatic Transfer Switch) supervision across multiple rooms â€” with a live web dashboard, alerting with debounce/hysteresis, offline-tolerant edge buffering, and role-based access control.

## Architecture

```
ESP8266 field nodes (firmware/)          Raspberry Pi 4              Cloud / VPS
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   MQTT   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  HTTPS   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ WEMOS_TS   (SHT30 + OLED)   â”‚ â”€â”€â”€â”€â”€â”€â”€â–¶ â”‚ HubBrain V5      â”‚ â”€â”€â”€â”€â”€â”€â”€â–¶ â”‚ HubGate V5 (FastAPI)    â”‚
â”‚ WEMOS_AC   (2x IR Gree AC)  â”‚ hs109rs/#â”‚ edge gateway     â”‚  X-Hub-* â”‚ â”œ REST API + RBAC       â”‚
â”‚ ATS bridge â†” FSM (serial)   â”‚ â—€â”€â”€â”€â”€â”€â”€â”€ â”‚ â”œ whitelist      â”‚ â—€â”€â”€â”€â”€â”€â”€â”€ â”‚ â”œ PostgreSQL            â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ downlink â”‚ â”œ WAL offline bufâ”‚ commands â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                      â”‚ same-origin
                                                                           Nginx (443, TLS) / Vite proxy
                                                                                     â”‚
                                                                            React SPA (gui-app)
```

- **Field nodes** publish telemetry over MQTT (`hs109rs/{ts,ats,ac}/data`) and receive downlink commands (`{hub}/{type}/command`).
- **HubBrain V5** (Raspberry Pi) filters traffic against a server-synced device whitelist, queues telemetry locally (SQLite WAL) when upstream is down, replays FIFO on reconnect, and resolves downlink topics dynamically.
- **HubGate V5** (FastAPI + PostgreSQL) ingests telemetry with discriminated-union payload validation, evaluates alerts synchronously (per-device debounce + hysteresis), queues device commands, and serves session-cookie auth (Argon2id, lockout, rate limiting).
- **SPA** (React 19 + TanStack Router/Query + Tailwind 4) polls live views every 3 s; same-origin topology means no CORS anywhere.

## Repository Layout

| Path | What it is |
|---|---|
| `firmware/` | ESP8266/Arduino node sketches (one folder per sketch, Arduino IDE compatible; `firmware/common/secrets.h` gitignored) |
| `hub/` | HubBrain V5 â€” Python edge gateway daemon for Raspberry Pi |
| `server/` | HubGate V5 â€” FastAPI cloud gateway, auth/RBAC, DB models, tests |
| `dashboard/` | React SPA |
| `docs/` | Guides: local testing, production deployment, hub backup, credential rotation, firmware proofing, runbooks |
| `tests/` | Repo-level E2E pipeline & deployment-verifier tests |
| `tools/` | Ops utilities: Pi deploy/backup, DB seeding, mock publishers, sniffers, verifiers |
| `deploy/` | Production deploy script + Nginx configs (prod & WSL staging) |
| `mosquitto/` | Local Mosquitto broker config (Docker) |

## Quickstart (local dev)

Prerequisites: Docker Desktop, Python 3.12+, Node 18+.

```powershell
# 1. Start PostgreSQL + Mosquitto containers
docker compose up -d

# 2. Initialize the API database (SQLite fallback works too)
cd server
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python init_sqlv5.py
python create_admin_user.py --help   # or tools/reset_sqlite_users.py

# 3. One-click launch: API on :8000 + SPA on :5173
#    (from repo root)
.\start_dev.ps1
```

Default local dev logins: `admin/admin123`, `operator/operator123`, `viewer/viewer123` (dev only).

## Tests & Verification

```powershell
pytest                # full suite at repo root (offline-safe, SQLite-backed)
cd dashboard
npm run lint          # oxlint
npm run build         # typecheck + production build
```

## Field Firmware

| Sketch | Node | Notes |
|---|---|---|
| `firmware/WEMOS_TS/` | Temperature/humidity (SHT30 + OLED) | dual I2C auto-probe, NaN-skip publishing, non-blocking loop |
| `firmware/WEMOS_AC/` | Dual AC/IR controller (IRGreeAC) | EEPROM state persistence across reboot |
| `firmware/fixed_wemos_mqtt_raspi/` | ATS bridge (MQTT â†” serial FSM) | canonical serial framing `<SGM,on>` `<M,auto>` â€¦ |
| `firmware/fsm_w_serial/` | ATS FSM controller (Arduino) | PLN/genset/backup-battery state machine |
| `firmware/HARDWARE_OLED_TEST/` | I2C bus recovery & OLED diagnostic utility | |


## Documentation

| Doc | Topic |
|---|---|
| `docs/LOCAL_TESTING_GUIDE.md` | Local Docker + mock publisher + E2E test stack |
| `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` | VPS + Raspberry Pi production runbook |
| `docs/HUB_BACKUP_GUIDE.md` | Raspberry Pi mandatory backup gate |
| `docs/CREDENTIAL_ROTATION_GUIDE.md` | Credential rotation procedure |
| `docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md` | Firmware proofing plan |
| `docs/runbooks/postgres_cutover_runbook.md` | Postgres cutover runbook |
| `AGENTS.md` (+ per-directory) | DOX work contracts for AI/agent development |

## Security Notes

- All hubâ†”server traffic is authenticated (`X-Hub-ID`/`X-Hub-Key` headers, constant-time compare) over verified TLS.
- Sessions: Argon2id password hashing, timing-safe verification, sliding expiry with absolute cap, per-username lockout, SlowAPI rate limits.
- **This repository intentionally excludes** real credentials (`.env`, broker passwd, TLS keys). Create your own from the `*.example` templates before deploying.
