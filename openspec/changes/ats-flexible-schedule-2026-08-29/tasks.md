# Tasks: ats-flexible-schedule-2026-08-29

> **Status:** COMPLETED & VERIFIED (2026-08-29)  
> **Implementation Commit:** `b4dcec6`  
> **Production Status:** Live in production since 2026-08-29; firmware autonomous fallback disabled 2026-08-31 (`dcfeb84`).  
> **Verification:** APScheduler BackgroundScheduler, CRUD endpoints, dashboard routes, and misfire/coalesce verified.  

## 1. Spec & scaffolding

- [x] 1.1 Create change folder `openspec/changes/ats-flexible-schedule-2026-08-29` with `.openspec.yaml` (status: proposed, created: 2026-08-29)
- [x] 1.2 Write `proposal.md` with D1-D5 decisions, RTC drift motivation, hub scaling, risks
- [x] 1.3 Write `design.md` with architecture diagram, shadcn list, APScheduler snippet, DB schema, timezone, firmware bundling
- [x] 1.4 Write `specs/dashboard-scheduling/spec.md` and `specs/server-scheduler/spec.md` (SHALL/WHEN/THEN)
- [x] 1.5 Verify `specs/` capabilities match proposal Impacts

## 2. Server scheduler

- [x] 2.1 Add `server/app/models/schedule.py` + Alembic migration `schedules(id,dev_id,hub_id,cron_expr,payload,tz,enabled)` + indexes
- [x] 2.2 Add `server/app/services/scheduler.py` with `BackgroundScheduler` + `SQLAlchemyJobStore` + `scheduler_lifespan` + `fire_schedule()` inserting into `pending_commands`
- [x] 2.3 Wire `lifespan` into `server/app/main.py` (`FastAPI(lifespan=scheduler_lifespan)`) and rehydrate jobs on start
- [x] 2.4 Cron validation via `cron-parser` (or `croniter`) before DB write; `cronstrue` preview helper endpoint `GET /api/schedules/preview?cron_expr=...`
- [x] 2.5 Handle `misfire_grace_time=60`, `coalesce=True`, `max_instances=1`; job id `schedule-{id}`
- [x] 2.6 Timezone `Asia/Jakarta` canonical, APScheduler `CronTrigger` timezone-aware

## 3. API CRUD `/api/schedules`

- [x] 3.1 `POST /api/schedules` — body `{dev_id, hub_id?, cron_expr, payload, tz?, enabled?}` admin-only; validates cron + payload whitelist, creates row + `scheduler.add_job`
- [x] 3.2 `GET /api/schedules` — list with filters `hub_id, dev_id, enabled`; includes `next_run` (cron-parser) + `human` (cronstrue)
- [x] 3.3 `GET /api/schedules/{id}` — detail
- [x] 3.4 `PATCH /api/schedules/{id}` — partial update, reschedules APScheduler job; toggle `enabled` adds/removes job
- [x] 3.5 `DELETE /api/schedules/{id}` — removes row + `scheduler.remove_job`
- [x] 3.6 RBAC: admin write, operator read-only; unauth 401, operator write 403; Pydantic validation 422 for bad cron/payload
- [x] 3.7 Add `queryKeys.schedules` factory and `api.ts` helpers

## 4. Dashboard UI (shadcn)

- [x] 4.1 Init shadcn: `npx shadcn@latest init` (style default, zinc, cssVariables true), add `@tailwindcss/vite` plugin to `vite.config.ts`, verify dark `background:#09090b` still applies
- [x] 4.2 Add primitives: `Dialog`, `Select`, `Calendar` (+ `react-day-picker`), `Popover`, `Table`, `Switch`, `Badge`, `Button`, `Input`, `Label`; keep `cn()` = `clsx + tailwind-merge`
- [x] 4.3 Add deps `cron-parser`, `cronstrue` for cron preview/validation
- [x] 4.4 Create route `dashboard/src/routes/schedules.tsx` + hooks polling not needed (invalidate on mutation); `Table` with human preview + enabled `Switch`
- [x] 4.5 `Dialog` form: `Select` hub/dev (ATS filtered), `Select` command preset (Warmup manual+on / Cooldown auto / RST / Custom), `Input` cron with live `cronstrue` preview (`useMemo`), `Popover`+`Calendar` next-run helper
- [x] 4.6 Wire `queryKeys.ts` + `api.ts` mutations, Zod `validateSearch` for filter params, error handling via `QueryCache.onError`
- [x] 4.7 Build check `npm run build` + `tsc -b` passes, bundle delta ~40-60 kB

## 5. Firmware / Hub contract (no code)

- [x] 5.1 Document bundled payload `{"mode":"manual","start_genset":"on"}` bypasses `check_genset_mode` (PROMINI `fsm_w_serial.ino`); note sequential `<M,manual>` then `<SGM,on>` via `fixed_wemos_mqtt_raspi.ino` 512B bounded serial
- [x] 5.2 Verify existing 2s `pending_commands` poll (hub) + `0.35s` WAL pacing handles burst; no hub code change
- [x] 5.3 Optional `durationSec` in payload for auto-off schedule; leave RTC as fallback display

## 6. Tests & verification

- [x] 6.1 `pytest` server: cron validation rejects bad expr (422), RBAC (operator 403), create->job exists, disable->job removed, timezone Asia/Jakarta, fire inserts `pending_commands`
- [x] 6.2 `pytest` misfire/coalesce: simulate downtime, coalesce to one fire
- [x] 6.3 Dashboard vitest: cron preview renders, Select picks payload, Dialog create flow, Table lists with Switch toggle, RBAC guard
- [x] 6.4 E2E: create schedule `0 18 * * 0` via API -> wait fire (or manual trigger) -> `pending_commands` row -> hub poll -> MQTT `{hub_name}/ATS/command` (mock) -> serial bundled
- [x] 6.5 `npm run lint` (oxlint) 0 errors, `docker compose config` still binds 127.0.0.1, `bash -n deploy/setup_push_deploy.sh`

## 7. Docs & closeout

- [x] 7.1 Update `docs/SESSION_HANDOVER.md` and researcher notes with scheduler + shadcn decisions
- [x] 7.2 DOX pass per `AGENTS.md` — no AGENTS.md edits needed unless new durable boundaries added
- [x] 7.3 `git log --all -- openspec/changes/` archive check, `graphify update .` if code touched
