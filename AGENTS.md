# AGENTS.md — smsb (root)

IoT smart-building monitoring system. Multi-component monorepo: a React SPA at `clients/gui-app/` (connected to live API via TanStack Query), a FastAPI cloud gateway at `SERVERv5/` (HubGate V5), a Raspberry Pi edge gateway at `HUBV5/` (HubBrain V5), ESP8266 node firmware at the root (`.ino`), and spec-driven change proposals in `openspec/`. Design spec at `2026-07-01-iot-temperature-monitoring-design.md`.

## Ownership

- **Root**: project-wide rules, DOX framework, global preferences, design docs, firmware `.ino` files, guides (`LOCAL_TESTING_GUIDE.md`, `HUB_BACKUP_GUIDE.md`, `PRODUCTION_DEPLOYMENT_GUIDE.md`), `FIRMWARE_ALIGNMENT_REPORT.md`, `researcher_notes.md`
- **clients/gui-app/**: SPA development — routes, TanStack Query hooks, minimal Zustand UI store, build tooling
- **SERVERv5/**: cloud gateway (HubGate V5) — FastAPI, auth/RBAC, DB, rooms/devices/alerts API, deploy scripts
- **HUBV5/**: edge gateway (HubBrain V5) — Raspberry Pi MQTT bridge, whitelist, offline WAL cache, HTTPS upstream
- **openspec/**: spec-driven change proposals & capability specs
- **graphify-out/**: auto-generated tool output, not edited directly

## DOX Framework

AGENTS.md files are binding work contracts for their subtrees. Parent docs define broad rules; child docs carry domain-specific instructions. Work must remain understandable from the nearest applicable AGENTS.md plus every parent above it.

**Read chain before editing:** root → walk to target path reading every AGENTS.md found → nearest doc is the local contract.

**Update after editing:** update closest owning AGENTS.md when purpose, structure, contracts, workflows, inputs/outputs, or user preferences change. Update parent docs when child index or parent-level structure changes. Remove stale text immediately.

## Commands

| Command | What it does |
|---|---|
| `start_dev.bat` or `.\start_dev.ps1` | 1-click launcher for HubGate V5 API (port 8000) & Vite SPA (port 5173) |
| `npm run dev` (in `clients/gui-app/`) | Vite HMR dev server with `/api` and `/static` proxy |
| `npm run build` (in `clients/gui-app/`) | `tsc -b && vite build` (typecheck first) |
| `npm run lint` (in `clients/gui-app/`) | `oxlint` (no ESLint/Prettier) |
| `pytest` (at repo root) | Run full automated test suite (105 tests) |
| `docker compose up -d` (at repo root) | Start local PostgreSQL and Eclipse Mosquitto containers |

## Stack

React 19.2.7, TypeScript 6.0.3, Vite 8.1.3, TanStack Router 1.170.17, TanStack Query 5.90.21, Zustand 5.0.14 (UI state only), Zod 4.4.3, Tailwind 4.3.2, oxlint 1.72.0, lucide-react, clsx, tailwind-merge. FastAPI, SQLAlchemy 2.0, PostgreSQL / SQLite fallback, Pydantic v2, SlowAPI, Argon2id.

## Architecture

- **Frontend**: TanStack Query manages server state (`api.ts`, `queryKeys.ts`) with live polling (3s interval) on Dashboard, Room Detail, Device Detail, Map, and Alerts. Minimal Zustand store handles client UI state (`sidebarOpen`, `selectedRoomId`). Session validation via `GET /api/auth/me`.
- **Backend (HubGate V5)**: FastAPI app with Argon2id auth, session cookies, rate limiting, and REST endpoints for rooms CRUD, device pairing/unpairing, floor plans, alerts with debounce/hysteresis, and telemetry ingestion.
- **Edge (HubBrain V5)**: Raspberry Pi daemon bridging MQTT topics (`hs109rs/#`) to upstream HTTPS with SQLite WAL offline buffer and FIFO replay on reconnection. Dynamic downlink topic resolution (`{hub_name}/{dev_type}/command`).
- **Firmware**: Non-blocking I2C probing, NaN sensor read skips, EEPROM AC state persistence, and canonical serial command framing (`<SGM,on>`, `<SGM,off>`, `<RST,rst>`, `<M,auto>`, `<M,manual>`).

## Firmware (`firmware/` — one sketch folder per node)

Node sketches deployed to field hardware and bridged through HUBV5.

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

Implemented, tested with `arduino-cli`, and documented in `FIRMWARE_ALIGNMENT_REPORT.md`. Folder name must always match the `.ino` name (Arduino IDE requirement).

## Project Structure

```
smsb/
├── AGENTS.md                        ← root DOX doc (this file)
├── README.md                        ← GitHub front page (architecture, quickstart)
├── .gitignore                       ← excludes secrets (.env/passwd/cert.key), dbs, build output
├── LOCAL_TESTING_GUIDE.md           ← local test stack guide (Docker + mock publishers + E2E)
├── HUB_BACKUP_GUIDE.md              ← Raspberry Pi mandatory backup gate guide
├── PRODUCTION_DEPLOYMENT_GUIDE.md   ← production VPS and Pi deployment runbook
├── FIRMWARE_ALIGNMENT_REPORT.md     ← firmware alignment and protocol reference report
├── SESSION_HANDOVER.md              ← session continuation handover documentation
├── start_dev.bat                    ← 1-click batch launcher for HubGate V5 & Vite SPA
├── start_dev.ps1                    ← 1-click PowerShell launcher with IP & Pi reachability check
├── docker-compose.yml               ← local PostgreSQL & Mosquitto container stack
├── firmware/                        ← all node sketches, one folder per sketch (Arduino IDE compatible)
│   ├── WEMOS_TS/WEMOS_TS.ino        ← temperature/humidity node (ESP8266)
│   ├── WEMOS_AC/WEMOS_AC.ino        ← AC/IR controller node (ESP8266)
│   ├── fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino ← ATS Wemos bridge (ESP8266)
│   ├── WEMOS_ATS/WEMOS_ATS.ino      ← ATS Wemos bridge, realigned fork (ESP8266)
│   ├── fsm_w_serial/fsm_w_serial.ino ← ATS FSM controller (Arduino Uno-class)
│   ├── PROMINI/PROMINI.ino          ← ATS FSM controller (Pro Mini/Uno-class)
│   └── HARDWARE_OLED_TEST/HARDWARE_OLED_TEST.ino ← I2C bus recovery / OLED diagnostic
├── clients/
│   └── gui-app/                     ← SPA (see its AGENTS.md for details)
├── SERVERv5/
│   └── v5/                          ← HubGate V5 FastAPI (see its AGENTS.md)
├── HUBV5/
│   └── V5/                          ← HubBrain V5 edge gateway (see its AGENTS.md)
├── openspec/
│   └── changes/                     ← spec-driven change proposals (see its AGENTS.md)
├── tests/                           ← repo-level E2E & verifier tests (see its AGENTS.md)
├── tools/                           ← ops utilities: Pi deploy/backup, seeding, sniffers (see its AGENTS.md)
├── deploy/                          ← Nginx configs & production deploy script (see its AGENTS.md)
├── mosquitto/                       ← local Mosquitto broker config for Docker (passwd gitignored)
└── firmware_build/                  ← arduino-cli build snapshots (gitignored, regenerable)
```

## Key TypeScript Quirks

- `erasableSyntaxOnly: true` — no enums, no namespaces, no `import type =`
- `verbatimModuleSyntax: true` — must use `import type` for type-only imports
- `@/*` → `./src/*` (aliased in Vite + tsconfig paths)
- Project references: `tsc -b` compiles app + node configs

## Non-Obvious Facts

- `routeTree.gen.ts` is auto-generated (TanStack Router Vite plugin) — never edit
- `App.css` is dead code (leftover Vite template, not imported)
- Same-origin topology: Vite proxy locally (`/api` → `8000`) and Nginx in production forward cookies transparently without CORS preflight
- Alerts evaluate synchronously during ingestion in `receive_iot` with per-device debounce windows and hysteresis recovery
- Edge HubBrain queues telemetry in local SQLite WAL (`edge_cache.db`) on upstream failure and replays FIFO on reconnect
- TanStack Query server-state modules live at `src/lib/api.ts` + `src/lib/queryKeys.ts` (+ `queryClient.ts`), types at `src/types/api.ts`

## Secrets & Pre-Public Checklist

The repo currently tracks **live credentials** by explicit decision (private while under campus development). Before making the repo public or handing it beyond the team, sanitize ALL of the following (values must also be rotated, since they will have existed in local history):

| Tier | Location | Secret |
|---|---|---|
| 1 | `HUBV5/V5/.env` (gitignored — keep it that way), `tools/deploy_pi_edge.py`, `tools/send_ac_command.py`, `tools/sniff_pi.py`, `tools/sniff_pi_mqtt.py`, `tools/stream_live_telemetry.py`, `tools/seed_demo_data.py`, `tools/verify_prod_env.py` (banned-value literals), all field `.ino` sketches (`MQTT_PASS`, WiFi password) | live MQTT_PASS / HUB_KEY / Pi SSH creds |
| 1 | `tests/test_verify_prod_env.py` L111/L113 | real secrets as test fixtures |
| 2 | `SERVERv5/v5/README.txt`, `HUBV5/V5/README.txt` sample configs; `start_dev.*` printed dev logins; `docker-compose.yml` postgres creds | weak/sample credentials |

Rules until then:
- NEVER add new hardcoded secrets; read from env/args (see `tools/AGENTS.md`)
- `.gitignore` already blocks `.env*`, `mosquitto/config/passwd`, `cert.key`, `*.db` — never weaken it
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
- File-based routing via TanStack Router — add new `.tsx` in `routes/`, gen file updates automatically
- Run `pytest` to verify all 105 backend, edge, and pipeline integration tests

## Verification

- `npm run lint` (oxlint) in `clients/gui-app/` before submitting changes
- `npm run build` in `clients/gui-app/` for typecheck + production build check
- `pytest` across repo for full automated test suite

## Child DOX Index

| Path | Scope |
|---|---|
| `clients/gui-app/AGENTS.md` | SPA development: routes, TanStack Query hooks, UI store, components |
| `SERVERv5/AGENTS.md` | Cloud gateway (HubGate V5): FastAPI endpoints, auth/RBAC, DB models, migrations, tests |
| `HUBV5/AGENTS.md` | Edge gateway (HubBrain V5): MQTT bridge, whitelist, offline WAL cache, topic resolver |
| `openspec/AGENTS.md` | Spec-driven change proposals & capability specs |
| `tests/AGENTS.md` | Repo-level E2E pipeline & deployment-verifier tests |
| `tools/AGENTS.md` | Ops utilities: Pi deploy/backup, DB seeding, mock publishers, sniffers, verifiers |
| `deploy/AGENTS.md` | Production deploy script & Nginx configs |

