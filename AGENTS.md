# AGENTS.md â€” smsb (root)

IoT smart-building monitoring system. Multi-component monorepo: a React SPA at `apps/web/` (connected to live API via TanStack Query), a FastAPI cloud gateway at `server/` (HubGate V5), a Raspberry Pi edge gateway at `hub/` (HubBrain V5), ESP8266 node firmware at `firmware/` (one folder per sketch, `firmware/common/secrets.h` gitignored), and spec-driven change proposals in `openspec/`. Design spec at `docs/2026-07-01-iot-temperature-monitoring-design.md`. Version suffix `V5` stays until a `V6` proposal lands (see `openspec/`).

## Ownership

- **Root**: project-wide rules, DOX framework, global preferences
- **docs/**: design spec, firmware alignment report, testing/deployment/backup guides, handover notes
- **apps/web/**: SPA development â€” routes, TanStack Query hooks, minimal Zustand UI store, build tooling
- **server/**: cloud gateway (HubGate V5) â€” FastAPI, auth/RBAC, DB, rooms/devices/alerts API, deploy scripts
- **hub/**: edge gateway (HubBrain V5) â€” Raspberry Pi MQTT bridge, whitelist, offline WAL cache, HTTPS upstream
- **openspec/**: spec-driven change proposals & capability specs
- **graphify-out/**: auto-generated tool output, not edited directly

## DOX Framework

AGENTS.md files are binding work contracts for their subtrees. Parent docs define broad rules; child docs carry domain-specific instructions. Work must remain understandable from the nearest applicable AGENTS.md plus every parent above it.

**Read chain before editing:** root â†’ walk to target path reading every AGENTS.md found â†’ nearest doc is the local contract.

**Update after editing:** update closest owning AGENTS.md when purpose, structure, contracts, workflows, inputs/outputs, or user preferences change. Update parent docs when child index or parent-level structure changes. Remove stale text immediately.

## Commands

| Command | What it does |
|---|---|
| `start_dev.bat` or `.\start_dev.ps1` | 1-click launcher for HubGate V5 API (port 8000) & Vite SPA (port 5173) |
| `npm run dev` (in `apps/web/`) | Vite HMR dev server with `/api` and `/static` proxy |
| `npm run build` (in `apps/web/`) | `tsc -b && vite build` (typecheck first) |
| `npm run lint` (in `apps/web/`) | `oxlint` (no ESLint/Prettier) |
| `pytest` (at repo root) | Run full automated test suite (107 tests) |
| `docker compose up -d` (at repo root) | Start local PostgreSQL and Eclipse Mosquitto containers |

## Stack

React 19.2.7, TypeScript ~6.0.2, Vite ^8.1.1, TanStack Router 1.170.17, TanStack Query 5.101.2, Zustand 5.0.14 (UI state only), Zod 4.4.3, Tailwind 4.3.2, oxlint 1.71, lucide-react, clsx, tailwind-merge. FastAPI, SQLAlchemy 2.0, PostgreSQL / SQLite fallback, Pydantic v2, SlowAPI, Argon2id.

## Architecture

- **Frontend**: TanStack Query manages server state (`api.ts`, `queryKeys.ts`) with live polling (3s interval) on Dashboard, Room Detail, Device Detail, Map, and Alerts. Minimal Zustand store handles client UI state (`sidebarOpen`, `selectedRoomId`). Session validation via `GET /api/auth/me`.
- **Backend (HubGate V5)**: FastAPI app with Argon2id auth, session cookies, rate limiting, and REST endpoints for rooms CRUD, device pairing/unpairing, floor plans, alerts with debounce/hysteresis, and telemetry ingestion. History endpoint downsamples to ~1000 time buckets via AVG when >1000 rows in window (prevents "frozen at oldest" cap).
- **Edge (HubBrain V5)**: Raspberry Pi daemon bridging MQTT topics (`hs109rs/#`) to upstream HTTPS with SQLite WAL offline buffer and FIFO replay on reconnection. Dynamic downlink topic resolution (`{hub_name}/{dev_type}/command`).
- **Firmware**: Non-blocking I2C probing, NaN sensor read skips, EEPROM AC state persistence, and canonical serial command framing (`<SGM,on>`, `<SGM,off>`, `<RST,rst>`, `<M,auto>`, `<M,manual>`).

## Firmware (`firmware/` â€” one sketch folder per node)

Node sketches deployed to field hardware and bridged through hub.

**Fleet AP standardization (2026-08-23)**: every hub Pi broadcasts an identical hidden AP (`smsb-iot` / WPA2, channel surveyed per room) at static `192.168.72.242`, so all ESP sketches share the same WiFi/broker constants and work in any room on any Pi without reflashing. `DEV_NAME` is boot-derived per node (`<TYPE>-<last4 MAC hex>`), replacing hardcoded names.

| Sketch | Node | Status |
|---|---|---|
| `firmware/WEMOS_TS/WEMOS_TS.ino` | Temperature/humidity node (SHT30, OLED) | Aligned to live hub (`hs109rs`, `192.168.72.242`); dual I2C auto-probing (`0x3C`/`0x3D` for OLED, `0x44`/`0x45` for SHT30); 1 Hz throttled display engine (zero Soft WDT resets); NaN float publish skip; live boot I2C diagnostics; zero blocking halts |
| `firmware/WEMOS_AC/WEMOS_AC.ino` | AC/IR controller (2x IRGreeAC, SHT30, OLED) | Aligned to live hub (`hs109rs`, `192.168.72.242`); dual I2C auto-probing; 1 Hz throttled display engine; NaN float publish skip; EEPROM raw state persistence (`0xAC` magic byte + `kGreeStateLength` 8B/unit); boot restore; zero blocking halts |
| `firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino` | ATS Wemos bridge (MQTT + serial to FSM) | Aligned to live hub (`hs109rs`, `192.168.72.242`); non-blocking OLED check & exponential backoff reconnect; `HUB_NAME`/`DEV_TYPE: "ATS"` payload; canonical serial command framing |
| `firmware/WEMOS_ATS/WEMOS_ATS.ino` | ATS Wemos bridge (MQTT + serial to FSM) | Realigned to canonical bridge (`fixed_wemos_mqtt_raspi.ino`): live broker `192.168.72.242`, `hs109rs/ats/*` topics, authenticated MQTT (`hubadmin`), full ATSData payload (`HUB_NAME`/`DEV_TYPE`/`EMERGENCY`), 512B PubSub buffer, bounded serial buffer, exponential backoff |
| `firmware/fsm_w_serial/fsm_w_serial.ino` | ATS FSM controller (Arduino Uno-class) | ATS FSM controller; communicates with bridge over serial UART using canonical protocol `<M,auto/manual>`, `<SGM,on/off>`, `<RST,rst>` |
| `firmware/PROMINI/PROMINI.ino` | ATS FSM controller (Pro Mini/Uno-class) | Non-blocking RTC degraded mode (no `while(1);` on RTC absence): warmup countdown disabled, FSM continues on `millis()` timing; canonical serial protocol |
| `firmware/HARDWARE_OLED_TEST/HARDWARE_OLED_TEST.ino` | I2C bus recovery / OLED diagnostic utility | bench tool, not deployed |

Implemented, tested with `arduino-cli`, and documented in `docs/FIRMWARE_ALIGNMENT_REPORT.md`. Folder name must always match the `.ino` name (Arduino IDE requirement).

## Project Structure

```
smsb/
â”œâ”€â”€ AGENTS.md                        â† root DOX doc (this file)
â”œâ”€â”€ README.md                        â† GitHub front page (architecture, quickstart)
â”œâ”€â”€ .gitignore                       â† excludes secrets (.env/passwd/cert.key), dbs, build output
â”œâ”€â”€ docs/                            â† design + guides (see below)
â”‚   â”œâ”€â”€ 2026-07-01-iot-temperature-monitoring-design.md
â”‚   â”œâ”€â”€ FIRMWARE_ALIGNMENT_REPORT.md â† firmware alignment and protocol reference
â”‚   â”œâ”€â”€ LOCAL_TESTING_GUIDE.md       â† local test stack guide
â”‚   â”œâ”€â”€ PRODUCTION_DEPLOYMENT_GUIDE.md â† production VPS and Pi deployment runbook
â”‚   â”œâ”€â”€ HUB_BACKUP_GUIDE.md          â† Raspberry Pi mandatory backup gate guide
â”‚   â”œâ”€â”€ SESSION_HANDOVER.md          â† session continuation handover
â”‚   â””â”€â”€ researcher_notes.md          â† scratch research notes
â”œâ”€â”€ start_dev.bat                    â† 1-click batch launcher for HubGate V5 & Vite SPA
â”œâ”€â”€ start_dev.ps1                    â† 1-click PowerShell launcher with IP & Pi reachability check
â”œâ”€â”€ docker-compose.yml               â† local PostgreSQL & Mosquitto container stack
â”œâ”€â”€ firmware/                        â† all node sketches, one folder per sketch (Arduino IDE compatible)
â”‚   â”œâ”€â”€ WEMOS_TS/WEMOS_TS.ino        â† temperature/humidity node (ESP8266)
â”‚   â”œâ”€â”€ WEMOS_AC/WEMOS_AC.ino        â† AC/IR controller node (ESP8266)
â”‚   â”œâ”€â”€ fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino â† ATS Wemos bridge (ESP8266)
â”‚   â”œâ”€â”€ WEMOS_ATS/WEMOS_ATS.ino      â† ATS Wemos bridge, realigned fork (ESP8266)
â”‚   â”œâ”€â”€ fsm_w_serial/fsm_w_serial.ino â† ATS FSM controller (Arduino Uno-class)
â”‚   â”œâ”€â”€ PROMINI/PROMINI.ino          â† ATS FSM controller (Pro Mini/Uno-class)
â”‚   â””â”€â”€ HARDWARE_OLED_TEST/HARDWARE_OLED_TEST.ino â† I2C bus recovery / OLED diagnostic
â”œâ”€â”€ clients/
â”‚   â””â”€â”€ gui-app/                     â† SPA (see its AGENTS.md for details)
â”œâ”€â”€ server/
â”‚   â””â”€â”€ v5/                          â† HubGate V5 FastAPI (see its AGENTS.md)
â”œâ”€â”€ hub/
â”‚   â””â”€â”€ V5/                          â† HubBrain V5 edge gateway (see its AGENTS.md)
â”œâ”€â”€ openspec/
â”‚   â””â”€â”€ changes/                     â† spec-driven change proposals (see its AGENTS.md)
â”œâ”€â”€ tests/                           â† repo-level E2E & verifier tests (see its AGENTS.md)
â”œâ”€â”€ tools/                           â† ops utilities: Pi deploy/backup, seeding, sniffers (see its AGENTS.md)
â”œâ”€â”€ deploy/                          â† Nginx configs & production deploy script (see its AGENTS.md)
â”œâ”€â”€ mosquitto/                       â† local Mosquitto broker config for Docker (passwd gitignored)
â””â”€â”€ firmware_build/                  â† arduino-cli build snapshots (gitignored, regenerable)
```

## Key TypeScript Quirks

- `erasableSyntaxOnly: true` â€” no enums, no namespaces, no `import type =`
- `verbatimModuleSyntax: true` â€” must use `import type` for type-only imports
- `@/*` â†’ `./src/*` (aliased in Vite + tsconfig paths)
- Project references: `tsc -b` compiles app + node configs

## Non-Obvious Facts

- `routeTree.gen.ts` is auto-generated (TanStack Router Vite plugin) â€” never edit
- `App.css`/`mockData.ts` removed (were dead Vite template code)
- Same-origin topology: Vite proxy locally (`/api` â†’ `8000`) and Nginx in production forward cookies transparently without CORS preflight
- Alerts evaluate synchronously during ingestion in `receive_iot` with per-device debounce windows and hysteresis recovery
- Edge HubBrain queues telemetry in local SQLite WAL (`edge_cache.db`) on upstream failure and replays FIFO on reconnect
- TanStack Query server-state modules live at `src/lib/api.ts` + `src/lib/queryKeys.ts` (+ `queryClient.ts`), types at `src/types/api.ts`

## Secrets & Pre-Public Checklist

The repo currently tracks **live credentials** by explicit decision (private while under campus development). Before making the repo public or handing it beyond the team, sanitize ALL of the following (values must also be rotated, since they will have existed in local history):

| Tier | Location | Secret |
|---|---|---|
| 1 | `hub/.env` (gitignored â€” keep it that way), `firmware/common/secrets.h` (gitignored â€” live WiFi/MQTT creds via `WIFI_PASS`/`MQTT_PASS` macros) | live MQTT_PASS / HUB_KEY / Pi SSH creds |
| 1 | `tests/test_verify_prod_env.py` L111/L113 | real secrets as test fixtures (banned-value literals for verifier) |
| 2 | `server/README.txt`, `hub/README.txt` sample configs; `start_dev.*` printed dev logins; `docker-compose.yml` postgres creds | weak/sample credentials |

> **Note (afb9c46)**: `tools/` scripts are now env-driven with no hardcoded live defaults â€” `deploy_pi_edge.py`, `send_ac_command.py`, `sniff_pi*.py`, `stream_live_telemetry.py`, `seed_demo_data.py` and others require `MQTT_PASS`/`HUB_KEY`/`PI_PASSWORD` via env or CLI args. `tools/verify_prod_env.py` banned-value literals are verifier fixtures, not deployed secrets. Field `.ino` sketches no longer embed secrets â€” they include `firmware/common/secrets.h` (gitignored; see `secrets.h.example`).

Rules until then:
- NEVER add new hardcoded secrets; read from env/args (see `tools/AGENTS.md`)
- `.gitignore` already blocks `.env*`, `mosquitto/config/passwd`, `cert.key`, `*.db` â€” never weaken it
- If a secret ever does get committed: rotate it immediately, then rewrite history before publishing

## CSS / Styling

- Tailwind 4 via `@tailwindcss/vite` (no PostCSS config)
- Dark theme: `--color-background: #09090b`, primary `#6366f1` (indigo)
- Inter font from Google Fonts
- `cn()` utility wraps clsx + tailwind-merge

## Work Guidance

- Server state queries & mutations must use TanStack Query hooks and the `queryKeys` factory
- Search params validated with Zod (`validateSearch` + `Route.useSearch()`)
- Sort/filter state in URL params, not component state
- File-based routing via TanStack Router â€” add new `.tsx` in `routes/`, gen file updates automatically
- Run `pytest` to verify all 107 backend, edge, and pipeline integration tests

## Verification

- `npm run lint` (oxlint) in `apps/web/` before submitting changes
- `npm run build` in `apps/web/` for typecheck + production build check
- `pytest` across repo for full automated test suite

## Child DOX Index

| Path | Scope |
|---|---|
| `apps/web/AGENTS.md` | SPA development: routes, TanStack Query hooks, UI store, components |
| `server/AGENTS.md` | Cloud gateway (HubGate V5): FastAPI endpoints, auth/RBAC, DB models, migrations, tests |
| `hub/AGENTS.md` | Edge gateway (HubBrain V5): MQTT bridge, whitelist, offline WAL cache, topic resolver |
| `openspec/AGENTS.md` | Spec-driven change proposals & capability specs |
| `tests/AGENTS.md` | Repo-level E2E pipeline & deployment-verifier tests |
| `tools/AGENTS.md` | Ops utilities: Pi deploy/backup, DB seeding, mock publishers, sniffers, verifiers |
| `deploy/AGENTS.md` | Production deploy script & Nginx configs |

