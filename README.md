# SMSB — Smart Building Monitoring System

IoT monitoring & control platform for building infrastructure: temperature/humidity sensing, AC (IR) control, and ATS (Automatic Transfer Switch) supervision across multiple rooms — with a live web dashboard, alerting with debounce/hysteresis, offline-tolerant edge buffering, and role-based access control.

## Architecture

```mermaid
flowchart LR
    subgraph Nodes["ESP8266 Field Nodes (firmware/)"]
        direction TB
        TS["WEMOS_TS<br/>(SHT30 + OLED)"]
        AC["WEMOS_AC<br/>(2x IR Gree AC)"]
        ATS["WEMOS_ATS + PROMINI<br/>(ATS Bridge & FSM Controller)"]
    end

    subgraph Edge["Raspberry Pi 4 (Edge Gateway)"]
        HB["HubBrain V5 Daemon<br/>- Device whitelist filtering<br/>- SQLite WAL offline buffer"]
    end

    subgraph Cloud["Cloud / VPS Server"]
        direction TB
        HG["HubGate V5 (FastAPI)<br/>- REST API + RBAC<br/>- PostgreSQL DB"]
        PROXY["Nginx (:443 TLS) / Vite Proxy"]
        SPA["React SPA (dashboard)"]

        HG <-->|REST API & Sessions| PROXY
        PROXY <-->|Same-Origin| SPA
    end

    TS -->|MQTT hs109rs/ts/data| HB
    AC <-->|MQTT hs109rs/ac/data & downlink| HB
    ATS <-->|MQTT hs109rs/ats/data & downlink| HB

    HB <-->|HTTPS POST (X-Hub-ID / X-Hub-Key)<br/>Telemetry sync & downlink queue| HG
```

- **Field nodes** publish telemetry over MQTT (`hs109rs/{ts,ats,ac}/data`) and receive downlink commands (`{hub}/{type}/command`).
- **HubBrain V5** (Raspberry Pi) filters traffic against a server-synced device whitelist, queues telemetry locally (SQLite WAL) when upstream is down, replays FIFO on reconnect, and resolves downlink topics dynamically.
- **HubGate V5** (FastAPI + PostgreSQL) ingests telemetry with discriminated-union payload validation, evaluates alerts synchronously (per-device debounce + hysteresis), queues device commands, and serves session-cookie auth (Argon2id, lockout, rate limiting).
- **SPA** (React 19 + TanStack Router/Query + Tailwind 4) polls live views every 3 s; same-origin topology means no CORS anywhere.

## Repository Layout

| Path | What it is |
|---|---|
| [`firmware/`](firmware/) | ESP8266/Arduino node sketches (one folder per sketch, Arduino IDE compatible; `firmware/common/secrets.h` gitignored) |
| [`hub/`](hub/) | HubBrain V5 — Python edge gateway daemon for Raspberry Pi |
| [`server/`](server/) | HubGate V5 — FastAPI cloud gateway, auth/RBAC, DB models, tests |
| [`dashboard/`](dashboard/) | React SPA |
| [`docs/`](docs/) | Guides: local testing, production deployment, hub backup, credential rotation, runbooks |
| [`tests/`](tests/) | Repo-level E2E pipeline & deployment-verifier tests |
| [`tools/`](tools/) | Ops utilities: Pi deploy/backup, DB seeding, mock publishers, sniffers, verifiers |
| [`deploy/`](deploy/) | Production deploy script + Nginx configs (prod & WSL staging) |
| [`mosquitto/`](mosquitto/) | Local Mosquitto broker config (Docker) |
| [`wiki/`](wiki/) | Architecture & engineering knowledge base (`wiki/index.md`) |

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
| [`firmware/PROMINI/`](firmware/PROMINI/) | ATS FSM controller (Arduino Pro Mini) | PLN/genset/backup-battery state machine, non-blocking millis, serial framing |
| [`firmware/WEMOS_ATS/`](firmware/WEMOS_ATS/) | ATS bridge (ESP8266 Wemos D1 Mini) | MQTT to serial FSM bridge, canonical framing `<SGM,on>`, `<M,auto>` |
| [`firmware/WEMOS_TS/`](firmware/WEMOS_TS/) | Temperature/humidity (SHT30 + OLED) | dual I2C auto-probe, NaN-skip publishing, non-blocking loop |
| [`firmware/WEMOS_AC/`](firmware/WEMOS_AC/) | Dual AC/IR controller (IRGreeAC) | EEPROM state persistence across reboot |

## Documentation

| Doc | Topic |
|---|---|
| [`docs/LOCAL_TESTING_GUIDE.md`](docs/LOCAL_TESTING_GUIDE.md) | Local Docker + mock publisher + E2E test stack |
| [`docs/PRODUCTION_DEPLOYMENT_GUIDE.md`](docs/PRODUCTION_DEPLOYMENT_GUIDE.md) | VPS + Raspberry Pi production runbook |
| [`docs/HUB_BACKUP_GUIDE.md`](docs/HUB_BACKUP_GUIDE.md) | Raspberry Pi mandatory backup gate |
| [`docs/CREDENTIAL_ROTATION_GUIDE.md`](docs/CREDENTIAL_ROTATION_GUIDE.md) | Credential rotation procedure |
| [`docs/runbooks/postgres_cutover_runbook.md`](docs/runbooks/postgres_cutover_runbook.md) | Postgres cutover runbook |
| [`wiki/index.md`](wiki/index.md) | Architecture & engineering knowledge base |
| [`AGENTS.md`](AGENTS.md) (+ per-directory) | DOX work contracts for AI/agent development |

## Security Notes

- All hub—server traffic is authenticated (`X-Hub-ID`/`X-Hub-Key` headers, constant-time compare) over verified TLS.
- Sessions: Argon2id password hashing, timing-safe verification, sliding expiry with absolute cap, per-username lockout, SlowAPI rate limits.
- **This repository intentionally excludes** real credentials (`.env`, broker passwd, TLS keys). Create your own from the `*.example` templates before deploying.
