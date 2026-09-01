# AGENTS.md — smsb (root)

## DOX Framework

- DOX is a highly performant AGENTS.md hierarchy, extended with two supporting layers: `wiki/` for compiled project knowledge and `notes/` for quick, unsynthesized capture
- Agent must follow DOX instructions across any edits

### Core Contract

- AGENTS.md files are binding work contracts for their subtrees: they say how to work
- `wiki/` files are compiled knowledge for their subtrees: they say what is true
- `notes/` files are staging snippets for their subtrees: unsynthesized observations not yet worth a full wiki page
- Never blend layers. A rule about what the agent must *do* belongs in AGENTS.md. A description of what something *is*, why it exists, or how it relates to other things belongs in `wiki/`. A quick fact not yet durable enough to write up properly belongs in `notes/`. A doc that drifts into the wrong layer must be split, not left mixed
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it, and from the nearest applicable wiki index plus every parent wiki index above it

### Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. At each scope visited, check for a `wiki/index.md` and a `notes/` folder. Skim both for anything relevant before writing code — this is where context-gap answers live (ownership, prior decisions, cross-service relationships) so you don't re-derive them from source every time

Do not rely on memory. Re-read the applicable AGENTS.md chain, wiki pages, and notes in the current session before editing.

### Update After Editing

Every meaningful change requires a DOX pass before the task is done, covering all three layers.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update the closest owning `wiki/` pages in the same pass when a change affects:

- a concept, entity's, or workstream's actual behavior, definition, status, or relationships
- something a future session would otherwise have to re-derive from source to know
- a page that now contradicts the code, or a gap where no page exists for something the change introduced

Drop a quick line in `notes/` instead, when a change surfaces something true and possibly useful, but too small or too unclear yet to justify writing a full wiki page.

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior, contracts, or durable facts may leave docs unchanged, but the DOX pass still must happen — decide, don't skip.

### Wiki

`wiki/` mirrors the AGENTS.md hierarchy: any scope with its own AGENTS.md may have its own `wiki/` folder and its own `wiki/index.md`. A scope with nothing durable to record has no wiki folder — don't create empty scaffolding.

**Population.** A new scope's wiki is not backfilled automatically. It's built when the user prompts for it (e.g. "build the wiki for the auth service"), scanning the scope's code, docs, and accumulated `notes/` into pages. Once a wiki exists for a scope, it's kept current automatically as part of the ordinary Update After Editing pass — no separate prompt needed for incremental updates, only for initial construction or a full resync.

**Page types.** One concept, entity, workstream, or source summary per file. Filename is the page's identity — don't represent the same thing under two paths.

- `concept` — a static idea, pattern, or convention used in the project
- `entity` — a concrete thing: a service, module, table, external system
- `workstream` — an ongoing or completed effort: status, history, and the decisions made along the way. Decisions live inside their workstream's history rather than as separate pages
- `source` — a summary of an external doc (RFC, design doc, spec) worth referencing repeatedly

Each page opens with frontmatter:

```yaml
---
type: concept | entity | workstream | source
governed_by: path/to/AGENTS.md
links: [wiki/relative/page.md, ...]
sources: [path/to/file.ts, commit:<sha>, notes/relative/note.md, ...]
updated: <date or commit>
---
```

Body is plain declarative prose: what this is, why it exists, how it relates to what's around it, and — for `workstream` pages — what's been tried and decided so far. No imperatives, no instructions — those belong in AGENTS.md.

**Two edge types.** `links:` are context edges — other pages worth knowing about, answering "what else do I need to know." `sources:` are evidence edges — the file, commit, or note a claim actually traces back to, answering "how do I know this is true." Don't conflate them: a page can link to a related concept it doesn't derive from, and cite a source it doesn't otherwise reference.

**Cross-linking.** Every AGENTS.md that owns a wiki scope carries a `Wiki` line pointing to its `wiki/index.md`. Every `wiki/index.md` links back up to its governing AGENTS.md via `governed_by`. This must be a real, walkable link on both sides, not a one-line mention.

**Index.** `wiki/index.md` lists every page in its scope with a one-line description, updated on every wiki write. One index per scope, not a single repo-wide index — this is what keeps the wiki usable as it grows.

**Retrieval.** No embeddings, no vector index. An agent finds context by starting at the nearest `wiki/index.md` (and the root one), following explicit links, and falling back to plain full-text search within `wiki/` if nothing links where it needs to go. This keeps the wiki fully auditable — you can see exactly which link chain produced any answer.

**Lint.** On request ("lint the wiki" / "audit the wiki"), check for: orphan pages with no inbound links, pages missing required frontmatter, links or sources pointing to things that no longer exist, and pages that contradict current source or their `governed_by` AGENTS.md. Fix or flag what's found; don't silently leave contradictions in place.

### Notes

`notes/` mirrors the same hierarchy as `wiki/` and AGENTS.md, one folder per scope that needs it, organized into topical files rather than one page per fact.

- No required frontmatter — notes are meant to be cheap to write
- A note is a distilled snippet, not a raw transcript: short, keyword-findable, plain text
- Notes accumulate until something in them is durable and clear enough to promote into a proper `wiki/` page with full frontmatter and links; once promoted, trim or remove the note so it doesn't sit around duplicating the wiki
- Notes are searched by plain keyword/full-text search, same as the wiki — no separate retrieval mechanism

### Corrections

If a human has directly edited a `wiki/` or `notes/` file, that edit outranks the agent's next write to that file. On the next Update After Editing pass touching that page, the agent merges its update around the human's edit rather than overwriting it, and if the two conflict, the agent flags the conflict instead of silently resolving it in its own favor.

### Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- A scope's `wiki/index.md` and `notes/`, when present, are reachable from its owning AGENTS.md
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

### Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Create a child `wiki/` or `notes/` alongside it only once there's something worth capturing for that scope, and only via the population step above
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Wiki
- Notes
- Child DOX Index

### Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist
- Wiki pages stay descriptive, not imperative — if a page tells the agent what to do, it's misfiled
- Notes stay short and unsynthesized — if a note reads like a finished page, promote it instead of polishing it in place

### Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning AGENTS.md and any affected parents or children
3. Update nearest owning wiki pages, respecting any human edits per Corrections
4. Add or trim `notes/` for anything durable-but-unclear surfaced by the change
5. Refresh every affected Child DOX Index and wiki index
6. Remove stale or contradictory text across all three layers
7. Run existing verification when relevant
8. Report any docs intentionally left unchanged and why

### User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md.

- Current: private campus LAN (no public), push via `git push prod main` to `100.108.98.30`, dashboard at `dashboard/` (Vite), server at `server/` (HubGate V5), hub at `hub/` (HubBrain V5), docs at `docs/`

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

React 19.2.7, TypeScript ~6.0.2, Vite 8.1.1, TanStack Router 1.170.17, Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2 (via `@tailwindcss/vite`), oxlint 1.71. FastAPI, SQLAlchemy 2.0, PostgreSQL/SQLite fallback, Pydantic v2, SlowAPI, Argon2id, APScheduler 3.10.4 + tzdata (Asia/Jakarta).

### Architecture

- **Frontend**: TanStack Query `api.ts`/`queryKeys.ts` poll 3s (`POLL_MS`) on live views, cache-first defaults (`keepPreviousData` global, `gcTime 5m`, `refetchOnWindowFocus`, `STALE_MS 10s` stale-while-revalidate, no blank refetch), decoupled `queryKeys.devices.detail(devId)` (`staleTime: 60s`, `refetchInterval: false`, `refetchOnWindowFocus: true`, focus/dirty guarded form sync), `useCommandLifecycle` (1.5s status polling against `GET /api/commands/{command_id}`, 12s timeout, double-dispatch lock), ATS HistoryChart 3-panel stacked layout (PLN Grid + Genset + Starter Battery DC with 11.8V/11.2V thresholds, independent auto-scaled 12% padding Y-axes, synced X-axis and lifted crosshair, range-adaptive polling: 15s for 6h/24h, manual for 7d/30d), wall-clock renders `id-ID` `Asia/Jakarta WIB` (server stores UTC), `ErrorBoundary` + `QueryCache.onError` + 401 redirect, Zustand only `sidebarOpen`/`selectedRoomId`, `GET /api/auth/me` session, shadcn `components/ui/*` + `schedules` route flexible cron `Asia/Jakarta` (server-authoritative warmup, no firmware Sunday auto).
- **Backend**: FastAPI `app/` routers (auth/hubs/rooms/devices/alerts/iot/commands/schedules) + `core/config` + `services/alert_engine,presence,scheduler` (APScheduler `BackgroundScheduler` `Asia/Jakarta` → `pending_commands` `{"mode":"manual","start_genset":"on"}` bundled bypass), `GET /api/devices/{dev_id}` (single-device detail with computed status & thresholds) and `GET /api/commands/{command_id}` (`CommandStatusResponse` delivery status check), Argon2id, cookies `httponly/secure/samesite=lax`, rate limit via `X-Real-IP`/`X-Forwarded-For` (`parts[0]`), telemetry `event_time` from hub `_hub_created_at` epoch (WAL replay) else `now_utc`, `alert_engine` evaluates temperature and ATS starter battery undervoltage (`BATTERY_WARNING` 11.8V / `BATTERY_CRITICAL` 11.2V, recovery $\ge 12.0\text{V}$, 60s debounce) and auto-resolves `ATS_EMERGENCY` when `PLN>210 && GENSET<80` (case-insensitive, stuck-latch suppression), `GET /health` unauth, history downsamples to ~1000 buckets via AVG, `schedules` table `cron_expr/payload/tz/enabled`.
- **Edge**: Pi bridges `hs109rs/#` → HTTPS, `MAX_PENDING_ROWS=20000` WAL FIFO `0.35s` pacing with `_hub_created_at` epoch injection on replay (preserves capture time across offline bursts), whitelist sync, dynamic `{hub_name}/{dev_type}/command`.
- **Firmware**: non-blocking I2C, NaN skip, EEPROM AC state (`0xAC`), canonical `<SGM,on>` `<RST,rst>` `<M,auto>` `<T,unixtime>` `<RTC_OK>` framing, `WDT 8S` `MCUSR` `VAC 210/190` hysteresis `SIZE 20/60`, `WARMUP disabled` (server `schedules` authoritative, no `Sunday 18:00` auto). Fleet AP `smsb-iot` `192.168.72.242`, `DEV_NAME=<TYPE>-<last4 MAC>`.

### Firmware Fleet

Every hub Pi broadcasts hidden `smsb-iot` WPA2 `192.168.72.242`; all ESP share WiFi/broker, `DEV_NAME` boot-derived. `WARMUP Sunday 18:00` autonomous removed `2026-08-31` — server `schedules` `Asia/Jakarta` authoritative via `pending_commands`. Field note: pre-`dcfeb84` firmware re-latches `EMERGENCY_GENSET` after `RST` when warmup overdue + genset disconnected (boot retries start `MAX` times) - `RST` alone cannot clear; flash canonical `PROMINI` + `WEMOS_ATS` to remediate.

| Sketch | Node | Status |
|---|---|---|
| `firmware/WEMOS_TS/WEMOS_TS.ino` | TS SHT30+OLED | dual I2C `0x3C/0x3D` `0x44/0x45`, 1Hz OLED, NaN skip |
| `firmware/WEMOS_AC/WEMOS_AC.ino` | AC/IR 2x Gree | dual I2C, EEPROM `0xAC` 8B/unit |
| `firmware/WEMOS_ATS/WEMOS_ATS.ino` | ATS bridge **canonical** | `HUB_NAME`/`DEV_TYPE: ATS`, 512B buf, bounded serial, backoff, `RTC_OK` `proofed dcfeb84` |
| `firmware/PROMINI/PROMINI.ino` | ATS FSM Pro Mini **canonical** | `WDT 8S` `MCUSR` `VAC 210/190` `SIZE 20/60` `RST exact` `MAX 3` `WARMUP disabled` server `schedules` |
| `firmware/archive/fsm_w_serial-2026-08-31/fsm_w_serial.ino` | bench ATS FSM daily 86400 (archived) | not deployed |
| `firmware/bench/HARDWARE_OLED_TEST/HARDWARE_OLED_TEST.ino` | bench I2C utility | not deployed |

Folder name must match `.ino` (Arduino IDE). See `docs/FIRMWARE_ALIGNMENT_REPORT.md`. `firmware/common/secrets.h` gitignored (see `secrets.h.example`).

### Project Structure

```
smsb/
├── AGENTS.md  README.md  .gitignore  LICENSE  justfile
├── docs/  2026-*-design.md  FIRMWARE_*.md  LOCAL_TESTING*.md  PRODUCTION_*.md  HUB_BACKUP*.md  SESSION_HANDOVER.md  researcher_notes.md
├── dashboard/  index.html  vite.config.ts  package.json  src/  e2e/  public/  components.json
├── server/  hubgatev5.py (shim)  app/  alembic/  requirements.txt  pyproject.toml  Dockerfile
├── hub/  main.py  requirements.txt  Dockerfile
├── firmware/  WEMOS_*/*.ino  fixed_*/  PROMINI/  archive/fsm_*-2026-08-31/  bench/HARDWARE_OLED_TEST/  common/secrets.h.example
├── deploy/  nginx_smsb.conf  smsb-api.service  hubbrain.service  setup_push_deploy.sh
├── tools/  deploy_pi_edge.py  verifiers  sniffers  seeders
├── tests/  test_e2e_pipeline.py  test_verify_*.py
├── openspec/  AGENTS.md  changes/ats-flexible-schedule-2026-08-29/
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
- `src/lib/api.ts` `queryKeys.ts` `queryClient.ts` `types/api.ts` `scheduleApi.ts` `cron.ts`

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

- `npm run lint` (oxlint) in `dashboard/` — 0 errors, 18 fast-refresh warns
- `npm run build` in `dashboard/` — `tsc -b && vite build` (hidden sourcemap)
- `npm run test -- --run` (vitest 42 tests across 6 suites) + `npx playwright test --list` in `dashboard/`
- `pytest` at root — 134 tests (server 89 + hub 13 + pipeline/verifier)
- `docker compose config` binds `127.0.0.1:5432/1883` (not `0.0.0.0`)
- `bash -n deploy/setup_push_deploy.sh` + `curl https://127.0.0.1/api/health` `{"status":"ok","db":"up"}`

## Wiki

- Root wiki scope: [wiki/index.md](wiki/index.md) — compiled project knowledge (entities, concepts, workstreams). Skim it before re-deriving context from source; it is the cross-service map of the smsb stack.

## Notes

- Root notes scope: `notes/` — quick unsynthesized capture, currently `notes/field-ops.md` (VPS access, field state, pending reflash).

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
