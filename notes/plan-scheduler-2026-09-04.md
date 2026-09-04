# Plan: Scheduler UI Flesh-Out — 2026-09-04

- **Proposal:** `openspec/changes/scheduler-ui-flesh-out-2026-09-04/proposal.md`
- **Design:** `openspec/changes/scheduler-ui-flesh-out-2026-09-04/design.md`
- **Tasks:** `openspec/changes/scheduler-ui-flesh-out-2026-09-04/tasks.md`
- **Spec:** `openspec/changes/scheduler-ui-flesh-out-2026-09-04/specs/scheduler-ui/spec.md`

**Goal:** easy (hide cron), dynamic (online AC/ATS/ACC ? AC `ON/OFF/SET_TEMP` vs ATS `mode/start_genset/reset`), edit/delete/toggle/run-now production-grade (optimistic + `sonner` + `AlertDialog` + `TIER2 6000ms`).

**Key decisions:** server `/preview` authoritative (debounced 300ms) not client `UTC+7`; `CronBuilder` (Daily/Weekdays/Weekly/Custom, `HH:mm` WIB, 7-chip) + `buildCron`/`parseCronToBuilderState`; payload branching `PRESETS_ATS` + `PRESETS_AC`; device picker `fetchDevices(active)` ? `online && is_active` per `dev_type` with search/empty-states; optional `GET /api/devices?dev_type=` server filter.

**Phases:** 1 utils/types/schemas/api, 2 dialog rebuild (`CronBuilder` + `PayloadForm/ATS+AC` + `ScheduleDialogV2`), 3 list polish optimistic, 4 tests/lint (Vitest `buildCron`/`payloadSchema`, Playwright flows, optional pytest `dev_type`).

**Risks:** cron drift client vs server, payload parity, polling staleness ? mitigated by server preview, Zod union, `TIER2` + optimistic.

**Sources:** `notes/research-scheduler-ui-2026-09-04.md`, `dashboard/src/routes/schedules.tsx`, `components/schedules/ScheduleDialog.tsx`, `server/app/routers/schedules.py:161-359`, `app/services/scheduler.py` (`CANONICAL_TZ`, `CronTrigger.from_crontab`, `JOB_DEFAULTS`).
