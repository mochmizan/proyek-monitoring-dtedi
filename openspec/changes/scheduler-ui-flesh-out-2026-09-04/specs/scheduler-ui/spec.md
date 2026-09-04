---
type: workstream
governed_by: openspec/AGENTS.md
links: [../../dashboard/AGENTS.md, ../../server/AGENTS.md, ../../wiki/index.md]
sources: [notes/research-scheduler-ui-2026-09-04.md, dashboard/src/routes/schedules.tsx, dashboard/src/components/schedules/ScheduleDialog.tsx, server/app/routers/schedules.py, server/app/services/scheduler.py, dashboard/src/lib/cron.ts, dashboard/src/lib/scheduleApi.ts, dashboard/src/lib/constants.ts]
updated: 2026-09-04
---

# Spec: scheduler-ui

## Capability: scheduler-visual-builder (hidden cron)

- **SHALL** hide 5-field cron behind a visual builder that generates `cron_expr` from user-friendly controls so a user who does not know cron can schedule.
  - WHEN user selects Frequency `Daily` and Time `07:30` THEN system generates `cron_expr "30 7 * * *"` and shows preview.
  - WHEN user selects `Weekdays (Mon-Fri)` and Time `18:00` THEN system generates `"0 18 * * 1-5"`.
  - WHEN user selects `Weekly`, picks `Sunday`, Time `18:00` THEN system generates `"0 18 * * 0"`.
  - WHEN user picks multiple weekdays `Mon, Thu` THEN system generates `"0 18 * * 1,4"`.
  - WHEN user selects `Custom` THEN system exposes raw 5-field `Input` with inline validation and server preview.
- **SHALL** use server `GET /api/schedules/preview?cron_expr=&tz=Asia/Jakarta` (debounced ~300ms) as source of truth for human text and next runs, not client `UTC+7` brute-force.
  - WHEN builder changes THEN system debounces and calls `/preview`; WHEN server returns `{human, next_runs}` THEN system renders `human` and `next_runs[0..2]` as `WIB` + `UTC`; WHEN server 422 THEN system shows validation error via toast/inline (not `alert`).
- **SHALL** render `DialogTitle` + `DialogDescription` and `aria-invalid`/`aria-describedby` per `components/ui/dialog.tsx` contract and focus first invalid on submit.
- **SHALL** keep TZ canonical `Asia/Jakarta` (disabled input) and validate via `ZoneInfo`.

## Capability: scheduler-dynamic-payload

- **SHALL** know online `AC` and `ATS` (and `ACC`) devices dynamically and allow setting either without hand-crafted JSON.
  - WHEN `GET /api/devices?status=active` returns devices THEN picker filters `online && is_active` per `status` (`DEVICE_OFFLINE_WINDOW_SECONDS` + `last_seen`) and `dev_type` (`ATS`/`AC`/`ACC`), with search and empty state per type.
  - WHEN user picks an `ATS` device THEN payload form shows `ATSCommand` controls (`mode auto/manual`, `start_genset on/off`, `reset rst`) and presets (`warmup manual+on`, `cooldown auto`, `sgm_on/off`, `reset`); WHEN user picks `AC` THEN form shows `ACCommand` (`target AC1/AC2`, `action ON/OFF/SET_TEMP`, `temp 16-30` required iff `SET_TEMP`) and presets (`AC1 ON/OFF/24C`, `AC2` variants, `20/24/26` temps).
- **SHALL** validate payload client-side via Zod union mirroring `server/app/schemas.py:ATSCommand`/`ACCommand` (`>=1` field, `temp` range) and server-side via `routers/schedules.py:_validate_payload`; WHEN invalid THEN toast `422` detail (no `alert`).
- **SHALL** not require `hub_id` from client (server resolves `hub_id=device.hub_id` per `routers/schedules.py:178`); WHEN editing THEN `dev_id` change re-resolves hub.

## Capability: scheduler-list-optimistic

- **SHALL** support edit, delete, toggle enabled, and run-now with production-grade feedback.
  - WHEN user toggles `enabled` THEN system performs optimistic `PATCH /api/schedules/{id} {enabled}` via `onMutate/cancelQueries/setQueryData`, rolls back on error with `sonner` toast, and invalidates `queryKeys.schedules.all` on settle.
  - WHEN user deletes THEN system shows `AlertDialog` (destructive) not `confirm()`, performs optimistic removal, rolls back on error, toasts success/error.
  - WHEN user clicks `Run now` THEN system calls `POST /api/schedules/{id}/run-now`, toasts "Queued to pending_commands", and invalidates list.
  - WHEN user edits THEN dialog hydrates from `ScheduleResponse` (`parseCronToBuilderState` + payload branching) and `PATCH`es `cron_expr/payload/tz/enabled`.
- **SHALL** poll list with `TIER2 6000ms` (`constants.ts:POLL_TIER2_ALERTS_MS` ±15% jitter), `staleTime 30s`, `keepPreviousData` on filter, and `refetchOnWindowFocus` for preview; RBAC: `admin` writes, `operator`/`viewer` reads (reads via `get_current_user`, writes via `require_admin`).
