# AGENTS.md — smsb (root)

## DOX Framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

### Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

### Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

### Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

### Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

### Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order: Purpose → Ownership → Local Contracts → Work Guidance → Verification → Child DOX Index

### Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

### Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

### User Preferences

- Record durable behavior changes here or in the relevant child AGENTS.md
- Current: private campus LAN (no public), push via `git push prod main` to `100.108.98.30`, dashboard at `dashboard/` (Vite), server at `server/`, hub at `hub/`, docs at `docs/`

---

## Purpose

IoT smart-building monitoring: React SPA at `dashboard/`, FastAPI gateway at `server/` (HubGate V5), Pi edge at `hub/` (HubBrain V5), ESP8266 firmware at `firmware/`, specs in `openspec/`. Design at `docs/2026-07-01-iot-temperature-monitoring-design.md`. `V5` suffix stays until `V6` proposal.

## Ownership

- **Root**: project-wide rules, DOX rail, global preferences
- **docs/**: design, firmware alignment, testing/deployment/backup guides, handover (no AGENTS.md, owned by root)
- **dashboard/**: SPA — routes, TanStack Query, Zustand UI, build
- **server/**: HubGate V5 — FastAPI, auth/RBAC, DB, rooms/devices/alerts API
- **hub/**: HubBrain V5 — MQTT bridge, whitelist, WAL cache, HTTPS upstream
- **firmware/**: node sketches (one folder per `.ino`, `firmware/common/secrets.h` gitignored) — owned by root
- **openspec/**: spec-driven proposals & capability specs
- **deploy/**: Nginx & systemd & push-deploy
- **tools/**: Pi deploy/backup, seeding, sniffers, verifiers
- **tests/**: repo-level E2E & verifiers
- **graphify-out/**: auto-generated, not edited

## Local Contracts

### Stack

React 19.2.7, TypeScript ~6.0.2, Vite 8.1.1, TanStack Router 1.170.17, Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2, oxlint 1.71. FastAPI, SQLAlchemy 2.0, PostgreSQL/SQLite fallback, Pydantic v2, SlowAPI, Argon2id.

### Architecture

- **Frontend**: TanStack Query `api.ts`/`queryKeys.ts` poll 3s (`POLL_MS`) on live views, `ErrorBoundary` + `QueryCache.onError` + 401 redirect, Zustand only `sidebarOpen`/`selectedRoomId`, `GET /api/auth/me` session.
- **Backend**: FastAPI `app/` routers (auth/hubs/rooms/devices/alerts/iot/commands) + `core/config` + `services/alert_engine,presence`, Argon2id, cookies `httponly/secure/samesite=lax`, rate limit via `X-Real-IP`/`X-Forwarded-For` (`parts[0]`), `GET /health` unauth, history downsamples to ~1000 buckets via AVG.
- **Edge**: Pi bridges `hs109rs/#` → HTTPS, `MAX_PENDING_ROWS=20000` WAL FIFO `0.35s` pacing, whitelist sync, dynamic `{hub_name}/{dev_type}/command`.
- **Firmware**: non-blocking I2C, NaN skip, EEPROM AC state (`0xAC`), canonical `<SGM,on>` `<RST,rst>` `<M,auto>` framing. Fleet AP `smsb-iot` `192.168.72.242`, `DEV_NAME=<TYPE>-<last4 MAC>`.

### Firmware Fleet

Every hub Pi broadcasts hidden `smsb-iot` WPA2 `192.168.72.242`; all ESP share WiFi/broker, `DEV_NAME` boot-derived.

| Sketch | Node | Status |
|---|---|---|
| `firmware/WEMOS_TS/WEMOS_TS.ino` | TS SHT30+OLED | dual I2C `0x3C/0x3D` `0x44/0x45`, 1Hz OLED, NaN skip |
| `firmware/WEMOS_AC/WEMOS_AC.ino` | AC/IR 2x Gree | dual I2C, EEPROM `0xAC` 8B/unit |
| `firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino` | ATS bridge canonical | `HUB_NAME`/`DEV_TYPE: ATS`, 512B buf, bounded serial, backoff |
| `firmware/WEMOS_ATS/WEMOS_ATS.ino` | ATS bridge alias (deprecated) | 12-line shim → `fixed_wemos` |
| `firmware/fsm_w_serial/fsm_w_serial.ino` + `PROMINI/PROMINI.ino` | ATS FSM | RTC degraded `rtcAvailable` (no `while(1)`), `WDT`, canonical serial |
| `firmware/HARDWARE_OLED_TEST/HARDWARE_OLED_TEST.ino` | bench I2C utility | not deployed |

Folder name must match `.ino` (Arduino IDE). See `docs/FIRMWARE_ALIGNMENT_REPORT.md`. `firmware/common/secrets.h` gitignored (see `secrets.h.example`).

### Project Structure

```
smsb/
├── AGENTS.md  README.md  .gitignore  LICENSE  justfile
├── docs/  2026-*-design.md  FIRMWARE_*.md  LOCAL_TESTING*.md  PRODUCTION_*.md  HUB_BACKUP*.md  SESSION_HANDOVER.md  researcher_notes.md
├── dashboard/  index.html  vite.config.ts  package.json  src/  e2e/  public/
├── server/  hubgatev5.py (shim)  app/  alembic/  requirements.txt  pyproject.toml  Dockerfile
├── hub/  main.py  requirements.txt  Dockerfile
├── firmware/  WEMOS_*/*.ino  fixed_*/  fsm_*/  PROMINI/  common/secrets.h.example
├── deploy/  nginx_smsb.conf  smsb-api.service  hubbrain.service  setup_push_deploy.sh
├── tools/  deploy_pi_edge.py  verifiers  sniffers  seeders
├── tests/  test_e2e_pipeline.py  test_verify_*.py
├── openspec/  AGENTS.md
├── mosquitto/  config/mosquitto.conf (passwd gitignored)
└── graphify-out/ (ignored)
```

### Key Quirks

- `erasableSyntaxOnly:true` + `verbatimModuleSyntax:true` → `import type` only
- `@/*` → `./src/*` (Vite + tsconfig)
- `tsc -b` project refs
- `routeTree.gen.ts` auto-generated (TanStack Router) — never edit
- Same-origin: Vite proxy `/api`→`8000` locally, Nginx `443` → `127.0.0.1:8000` prod (no CORS)
- Alerts sync in `receive_iot` with debounce/hysteresis; edge WAL FIFO replay
- `src/lib/api.ts` `queryKeys.ts` `queryClient.ts` `types/api.ts`

### Secrets & Pre-Public Checklist

Private campus repo by decision. Before public, sanitize + rotate (lived in history):

| Tier | Location | Secret |
|---|---|---|
| 1 | `hub/.env` (gitignored), `firmware/common/secrets.h` (gitignored via `WIFI_PASS`/`MQTT_PASS`) | live MQTT_PASS / HUB_KEY / Pi SSH |
| 1 | `tests/test_verify_prod_env.py:111/113` verifier fixtures | banned-value literals |
| 2 | `server/README.txt` `hub/README.txt` samples; `start_dev.*` dev logins; `docker-compose.yml` postgres `postgres` | weak/sample |

Note (afb9c46): `tools/` env-driven (`MQTT_PASS`/`HUB_KEY`/`PI_PASSWORD` via env/args, no hardcoded defaults); `verify_prod_env.py` literals are verifier fixtures; `.ino` include `common/secrets.h` (gitignored).

Rules: never add hardcoded secrets; `.gitignore` blocks `.env*` `passwd` `cert.key` `*.db` — never weaken; if committed, rotate + `filter-repo` before publish.

### Style

- Tailwind 4 via `@tailwindcss/vite`, no PostCSS; dark `--color-background:#09090b`, primary `#6366f1`; `cn()` = `clsx + tailwind-merge`

## Work Guidance

- Server state via TanStack Query hooks + `queryKeys` factory (`POLL_MS`/`STALE_MS` in `constants.ts`)
- Search params Zod `validateSearch` + `Route.useSearch()`, sort/filter in URL not component state
- File routes in `routes/` — `routeTree.gen.ts` auto-updates
- `just` is runner: `just dev` (replaces `start_dev.ps1`), `just test` `just lint` `just build` `just firmware-check` `just deploy-dry-run`
- Keep `server/app/` routers/services split, `hub/main.py` bounded WAL, firmware `char[65]` bounded serial

## Verification

- `npm run lint` (oxlint) in `dashboard/` — 0 errors, 14 fast-refresh warns
- `npm run build` in `dashboard/` — `tsc -b && vite build` (hidden sourcemap)
- `npm run test -- --run` (vitest 3 smoke) + `npx playwright test --list` in `dashboard/`
- `pytest` at root — 107 tests (server 79 + hub 13 + pipeline)
- `docker compose config` binds `127.0.0.1:5432/1883` (not `0.0.0.0`)
- `bash -n deploy/setup_push_deploy.sh` + `curl https://127.0.0.1/api/health` `{"status":"ok","db":"up"}`

## Child DOX Index

| Path | Scope |
|---|---|
| `dashboard/AGENTS.md` | SPA — routes, Query hooks, ErrorBoundary, constants, vitest/playwright |
| `server/AGENTS.md` | HubGate V5 — FastAPI `app/` routers/services, auth/RBAC, DB/alembic, /health |
| `hub/AGENTS.md` | HubBrain V5 — MQTT bridge, whitelist, WAL `MAX_PENDING_ROWS`, TLS pin |
| `openspec/AGENTS.md` | Spec proposals & capability specs (changes pruned, archived in git) |
| `tests/AGENTS.md` | Repo E2E & verifier tests |
| `tools/AGENTS.md` | Pi deploy/backup, seeding, sniffers, verifiers |
| `deploy/AGENTS.md` | Nginx & systemd & push-deploy |

## graphify

Knowledge graph at `graphify-out/` (god nodes, communities). `/graphify` skill: `graphify query "<q>"`, `path`, `explain`. `graphify-out/` dirty after hooks is expected; skip only if stale. After code change run `graphify update .`.
