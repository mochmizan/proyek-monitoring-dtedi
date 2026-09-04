# Proposal: Scheduler UI Flesh-Out — Production-Grade Easy/Dynamic Schedule Management

## Summary

Flesh out the scheduler subsystem from backend-complete / frontend-partial to production-grade easy-to-use, dynamic, and auditable. Backend (`server/app/routers/schedules.py:161-359`, `server/app/services/scheduler.py`) already exposes 7 endpoints with RBAC, 5-field cron validation via `CronTrigger.from_crontab` canonical `Asia/Jakarta`, APScheduler `BackgroundScheduler` `coalesce/max_instances/misfire_grace_time=60`, and payload whitelisting (`ATSCommand`/`ACCommand`). Dashboard (`dashboard/src/routes/schedules.tsx`, `dashboard/src/components/schedules/ScheduleDialog.tsx`, `dashboard/src/lib/cron.ts`) is ATS-only, raw-cron `Input`, client `UTC+7` next-run drift, `alert()`/`confirm()`, no polling, no AC. This change hides cron behind a visual builder, makes device/payload forms dynamic per online `AC`/`ATS`/`ACC`, and hardens edit/delete/toggle/run-now to optimistic TanStack Query + toast + `TIER2` polling — no new hub/firmware work.

## Motivation

- **Ops goal (user prompt):** easy-to-use (user doesn't know cron), dynamic (knows online AC/ATS, can set either), edit & delete capable, production quality.
- **Current gap (per `notes/research-scheduler-ui-2026-09-04.md`):**
  - Easy: 7 `PRESETS` in `ScheduleDialog.tsx:PRESETS` are ATS-only; cron is raw `Input` with 4 quick-pills; `dashboard/src/lib/cron.ts:describeCron` handles 3 strings; next-run uses brute-force `UTC+7` not `ZoneInfo` ? diverges from server `get_next_runs`/`human_cron` in `scheduler.py:get_next_runs`/`human_cron`.
  - Dynamic: `schedules.tsx:atsDevices` filters `dev_type==="ATS"` client-side; `GET /api/devices` (`server/app/routers/devices.py:GET /api/devices`) has no `dev_type` filter; picker shows offline/disabled; zero `ACCommand` presets (`target AC1/AC2`, `action ON/OFF/SET_TEMP temp 16-30` per `server/app/schemas.py:ACCommand`).
  - Production-grade: `alert()`/`confirm()`, `invalidateQueries` only, no `onMutate` rollback, no `sonner`/toast, no `TIER2 6000ms` polling (`dashboard/src/lib/constants.ts:POLL_TIER2_ALERTS_MS`), missing `DialogTitle` a11y, no server `/preview` debounce.
- **Firmware/hub intact:** `hub/main.py:hubPollLoop` `2s` + WAL `MAX_PENDING_ROWS=20000` `0.35s` + `_hub_created_at`, `firmware/PROMINI/PROMINI.ino` `WARMUP disabled`, `WEMOS_AC/WEMOS_AC.ino` Gree IR — no change needed; bundled `{"mode":"manual","start_genset":"on"}` already bypasses PROMINI guard.

## What Changes

- **Dashboard — builder & dialog (breaking UX, no API break):**
  - New `CronBuilder` component (frequency `Select` ? Daily / Weekdays Mon-Fri / Weekly / Custom; `Input type="time"` 24h WIB; weekday 7-chip `ToggleGroup`; generator `buildCron({frequency,time,weekdays})?"m H * * dow"`; raw `cron_expr` collapsible for power users).
  - Refactor `ScheduleDialog` ? `ScheduleDialogV2` (or in-place refactor) with: dynamic device picker (`AC`/`ATS`/`ACC` tabs, search, `online && is_active` filter, empty states per type), payload branching (`ATSCommand` checkboxes vs `ACCommand` `target`/`action`/`temp`), server-authoritative preview (`GET /api/schedules/preview` debounced 300ms, `cronstrue` or server `human` for human text, `next_runs`), Zod parity (`scheduleCreateSchema` in `scheduleApi.ts`), `DialogTitle`/`Description` a11y, `sonner` toasts, `AlertDialog` for delete.
  - Retire or keep as fallback: `dashboard/src/lib/cron.ts:parseField/validateCron/getNextRuns` (client drift) — prefer server preview; keep `describeCron` as offline fallback or replace with `cronstrue`.
- **Dashboard — list page hardening:**
  - `schedules.tsx`: `TIER2 6000ms` polling (`refetchInterval: POLL_TIER2_ALERTS_MS` with jitter), `keepPreviousData` on filter, `staleTime 30s`, optimistic `update/delete/toggle/run-now` mutations (`cancelQueries` + `setQueryData` + rollback + `onSettled invalidate`), toast not `alert`, `AlertDialog` for delete, badge/payload rendering per `dev_type`, overlap hint.
- **Lib & types:**
  - `scheduleApi.ts`: tighten `cronExprSchema` (relax regex to allow `*`, `1-5`, `*/n`; delegate to `validateCron`/`preview`); add `atsPayloadSchema`/`acPayloadSchema` union `>=1` field; export `buildCron`/`parseCronToBuilderState`.
  - `api.ts` `previewScheduleCron` + `fetchDevices` optional `dev_type` param (gated on backend).
  - `queryKeys.ts`: keep `schedules.{all,list,detail,preview}`; preview key already `preview(cron,tz)`.
  - `constants.ts`: no new tier; use existing `POLL_TIER2_*`/`STALE_TIER2_*`.
- **Server — minimal/optional:**
  - Validate existing 7 endpoints suffice (they do). Optional enhancement: `GET /api/devices?dev_type=ATS|AC|ACC` trivial `WHERE dev_type` to avoid client-side filter (propose, behind feature flag — not required to ship).
  - No `schedules` table migration; no APScheduler config change.
- **Testing & quality:**
  - Vitest for `buildCron`/`parseCron`/`payloadSchema`, Playwright for create?toggle?edit?run-now?delete flows, pytest only if `devices.py` gets `dev_type` filter.

## Capabilities

### New
- `scheduler-visual-builder`: hide cron, generate from UI state, server preview source of truth.
- `scheduler-dynamic-payload`: AC vs ATS branching, online filtering, search, per-type empty states.

### Modified
- `dashboard-scheduling` (from `ats-flexible-schedule-2026-08-29`): from ATS-only raw cron to AC+ATS visual builder with optimistic mutations.
- `schedules-api-surface` (read-only): preview becomes primary UX; optional `dev_type` filter.

## Impact

- **Code:** `dashboard/src/routes/schedules.tsx`, `dashboard/src/components/schedules/ScheduleDialog.tsx` (? `ScheduleDialogV2.tsx` + `CronBuilder.tsx` + `PayloadForm/`), `dashboard/src/lib/cron.ts`, `scheduleApi.ts`, `api.ts`, `types/api.ts`, `queryKeys.ts`; optionally `server/app/routers/devices.py`.
- **Database:** none (optional `dev_type` index already exists via `dev_table`).
- **Edge/Firmware:** none; payload contracts unchanged (`server/app/schemas.py:ATSCommand`/`ACCommand`).
- **Ops:** no deploy change; `sonner` dep (+~8kB), `cronstrue` optional (+~6kB) — keep bundle <60kB delta; lazy-load dialog already via `React.lazy`.
- **Risks:** see `design.md`.

## Risks / Mitigations

- Client/server cron drift (`UTC+7` vs `ZoneInfo`) ? server `/preview` authoritative (see design).
- Payload validation bypass ? Zod union parity + server 422 ? toast.
- Offline device scheduling ? `online && is_active` filter + warning if none.

## Alternatives Considered

- Bundle `cron-parser` client-side: rejected (adds ~15kB, still drifts vs server APScheduler); prefer server preview + `cronstrue` for human.
- Keep raw cron as primary: rejected — fails "user doesn't know cron" goal.
- New `schedules` columns (`last_run_at`/`run_count`): deferred — `pending_commands` + `device_events` sufficient for v1.

## Out of Scope (Non-Goals)

- Edge-local cron, PROMINI RTC re-enable, new `schedules` table columns, Telegram push, multi-VPS, `hostapd`/`dnsmasq`/OverlayFS, `fsm_w_serial-2026-08-31` bench.
