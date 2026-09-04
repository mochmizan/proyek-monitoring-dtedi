# Design: Scheduler UI Flesh-Out

## Context

Single VPS `100.108.98.30` with PostgreSQL 16 prod / SQLite WAL dev, FastAPI `HubGate V5` (`server/app/main.py`), Vite SPA at `dashboard/` (React 19, TanStack Router/Query, Zustand, Zod, shadcn, Tailwind 4 via `@tailwindcss/vite`), Pi edge `HubBrain V5` (`hub/main.py` `2s` poll, WAL `20000` `0.35s`).

Scheduler is the only VPS-authoritative automation after `WARMUP disabled 2026-08-31` (`PROMINI` `WDT 8S` `VAC 210/190` `SIZE 20/60` `MAX 3`, `WEMOS_ATS` 512B). Server gives 7 endpoints (`routers/schedules.py:161-359`) with `require_admin` writes, `CANONICAL_TZ=Asia/Jakarta` (`services/scheduler.py:CANONICAL_TZ`), `CronTrigger.from_crontab`, `BackgroundScheduler` `SQLAlchemyJobStore` (PG) / memory+rehydrate (SQLite), `JOB_DEFAULTS coalesce/max_instances/misfire_grace_time=60`, `schedules` table `modelsv5.py:233` `ix_schedules_enabled_hub/dev`. Dashboard list is functional but ATS-only, raw cron, client `getNextRuns` `UTC+7` drift, `alert`/`confirm`, no `TIER2` polling, no AC. Research brief `notes/research-scheduler-ui-2026-09-04.md` synthesizes 3 audits and prescribes hide-cron + optimistic + `TIER2` + dynamic AC/ATS.

## Goals / Non-Goals

**Goals:** (1) Hide cron — user never hand-writes 5-field; (2) Dynamic — picker knows online `AC`/`ATS`/`ACC`, payload adapts; (3) Edit/delete/toggle/run-now feel production (optimistic + toast + `AlertDialog`); (4) Server preview truth; (5) RBAC `admin` vs `operator`/`viewer`; (6) TZ `Asia/Jakarta` correct; (7) Keep bundle lean, a11y shadcn-compliant.

**Non-Goals:** DB migration, new APScheduler tuning, hub/firmware change, edge cron, `last_run_at` columns, overlap blocking, SSE/WebSocket, Redis, Convex, `pg_cron`, `hostapd`/`dnsmasq`/OverlayFS, `fsm_w_serial` bench.

## Decisions

| ID | Topic | Verdict | Rationale |
|----|-------|---------|-----------|
| D1 | Cron source of truth | **Server `/preview` debounced 300ms; client `cron.ts` fallback only** | `scheduler.py:get_next_runs` uses `CronTrigger.from_crontab(..., timezone=CANONICAL_TZ)` — only server knows true `next_run_at`. Client `UTC+7` in `cron.ts:getNextRuns` diverges on DST-adjacent/historical and on `*/n`/`1-5` edge. |
| D2 | Human text | **`cronstrue` + server `human`/`human_cron`; retire custom `describeCron` 3-string** | `cronstrue.toString(cron,{use24HourTimeFormat:true})` is 6kB, covers 95%; server `human_cron`/`cron_descriptor` provides canonical fallback. Custom 3-string is insufficient. |
| D3 | Builder scope | **Frequency `Daily|Weekdays|Weekly|Custom`, time `HH:mm` 24h WIB, weekday 7-chip, raw collapsible** | Covers 95% warmup/AC cases (`0 18 * * 0`, `0 7 * * *`, `0 18 * * 1,4`, `*/30 * * * *` via Custom). Power users keep raw. |
| D4 | Payload branching | **Split `PRESETS_ATS` (existing 7) + `PRESETS_AC` (AC1/AC2 x ON/OFF/SET_TEMP 20/24/26)** | Backend whitelists both (`_validate_payload` tries `ATSCommand` then `ACCommand`). UI currently ATS-only; AC matrix makes AC visible without JSON. |
| D5 | Device picker source | **Query `fetchDevices(status="active")` then derive `online && is_active && dev_type`; optional `GET /api/devices?dev_type=` server filter** | Existing `GET /api/devices` already computes `status online/offline` via `DEVICE_OFFLINE_WINDOW_SECONDS` + `last_seen` and `is_active`; currently no `dev_type` param — client filter works today, server param is O(1) `WHERE dev_type=:t` enhancement if adopted. |
| D6 | Mutations | **TanStack optimistic `onMutate/cancelQueries/setQueryData/rollback/onSettled invalidate` + `sonner` toast + `AlertDialog`** | Replaces `alert`/`confirm`/`invalidate-only`; fixes rapid-toggle race. Pattern already in `room.$roomId.tsx`/`device.$deviceId.tsx` for commands. |
| D7 | Polling | **`schedules.list` `refetchInterval: POLL_TIER2_ALERTS_MS (6000)` with ±15% jitter; `preview` `staleTime 30s` `refetchOnWindowFocus`** | Matches `room.$roomId.tsx` map `TIER2`; keeps badge/switch convergent. Current `refetchInterval:false` is stale. |
| D8 | File strategy | **New `CronBuilder.tsx` + `PayloadForm/{ATSForm,ACForm}.tsx` + `ScheduleDialogV2.tsx` (or in-place refactor with feature flag); keep `ScheduleDialog.tsx` until cutover** | Keeps diff reviewable; `React.lazy` already in `schedules.tsx`. Rename on merge or keep V2. |
| D9 | cron.ts fate | **Deprecate `parseField/validateCron/getNextRuns` or keep behind `__LEGACY_CRON__` flag for offline fallback; export `buildCron/parseCronToBuilderState`** | Avoid drift; retain for tests/offline. |
| D10 | A11y | **`DialogTitle`+`Description` (sr-only allowed), `aria-invalid`/`aria-describedby`, focus first invalid on submit** | `components/ui/dialog.tsx` contract; current dialog violates. |

## Architecture

```
Dashboard: CronBuilder {freq, time, weekdays} --buildCron--> cron_expr --debounce 300ms--> GET /api/schedules/preview?cron_expr=&tz=Asia/Jakarta --> {human, next_runs}
         DevicePicker {tabs AC/ATS/ACC, search} <- fetchDevices(active) <- GET /api/devices?status=active[&dev_type=]
         PayloadForm  {ATS: mode/start_genset/reset  vs  AC: target/action/temp 16-30}
                    --Zod scheduleCreateSchema--> POST|PATCH /api/schedules {dev_id, cron_expr, payload, tz, enabled}
VPS:  APIScheduler BackgroundScheduler CronTrigger.from_crontab(..., timezone=Asia/Jakarta) -> pending_commands {hub_id, dev_id, payload}
Hub:  hub/main.py poll GET /api/hub/commands?hub_id= every 2s -> MQTT {hub_name}/{dev_type}/command -> WEMOS_ATS / WEMOS_AC -> PROMINI serial
```

- **No hub_id from client:** `routers/schedules.py:178` resolves `hub_id=device.hub_id`; dialog stops sending `hub_id` (or sends nullable for compat).
- **Rate limits:** writes `30/min`, reads/preview `30-60/min` via `X-Real-IP` `parts[0]` (see `core/config.py:limiter`) — preview debounce respects it.

## UX Design

### Visual cron builder (`CronBuilder.tsx`)

- **Frequency `Select`:** `Daily` ? `"m H * * *"`, `Weekdays (Mon-Fri)` ? `"m H * * 1-5"`, `Weekly` ? pick 1+ weekdays, `Custom` ? full 5-field.
- **Time:** `Input type="time"` step 60, 24h WIB, value `HH:mm` ? `m H`.
- **Weekday chips:** 7 `Button variant="outline"` toggles `Mon..Sun` ? 5th field `0` Sun, `1-5` etc; `Weekdays` preset auto-sets `1-5`; `Daily` disables chips.
- **Generator:** `buildCron({frequency,time,weekdays})` pure function; `parseCronToBuilderState(cron)` for edit hydrate.
- **Raw collapsible:** `Collapsible` / `details` with `Input` bound to same `cron_expr`; validates via server preview on change; client `validateCron` only for immediate inline error before server round-trip.
- **Preview panel:** `human` from server (`preview.human` or `cronstrue`), `next_runs[0..2]` via `formatNextRun` ? `jakarta WIB` + `UTC` muted; empty/error state: "Invalid cron — check fields".
- **TZ:** `Input` disabled `Asia/Jakarta` (canonical) — no user TZ pick in v1.

### Device picker

- Tabs or `ToggleGroup` `AC | ATS | ACC | All` (default `ATS` if exists else `AC`), counts per tab.
- Source: `useQuery(queryKeys.devices.list("active"), () => fetchDevices("active"))` then:
  ```ts
  const onlineATS = devices.filter(d => d.dev_type==="ATS" && d.is_active && d.status==="online")
  const onlineAC  = devices.filter(d => d.dev_type==="AC"  && d.is_active && d.status==="online")
  const onlineACC = devices.filter(d => d.dev_type==="ACC" && d.is_active && d.status==="online")
  ```
- Search `Input` filter by `dev_name`/`dev_id` substring.
- Empty states: "No online ATS — pair one in Settings" / "No online AC — pair one" (not generic).
- When `GET /api/devices?dev_type=` ships, switch to `fetchDevices("active", dev_type)` per tab to avoid over-fetch.

### Payload builder (branching)

- **ATS:** checkboxes `mode auto/manual` (radio), `start_genset on/off`, `reset rst`; bundled warmup `{"mode":"manual","start_genset":"on"}` is a preset button.
- **AC:** `Select target AC1/AC2` ? `Select action ON/OFF/SET_TEMP` ? conditional `Input type="number" min=16 max=30` for `temp` (required iff `SET_TEMP`; `zod refine`).
- **Presets:** `PRESETS_ATS` (keep 7) + `PRESETS_AC`:
  ```
  AC1 ON  ? {"target":"AC1","action":"ON"}
  AC1 OFF ? {"target":"AC1","action":"OFF"}
  AC1 24C ? {"target":"AC1","action":"SET_TEMP","temp":24}
  AC2 ON/OFF/24C similarly; extras 20C/26C
  ```
  Selecting preset populates `PayloadForm`; `Custom JSON` `textarea` remains for power users.
- **Overlap hint (non-blocking):** if `existingSchedules.some(s=>s.dev_id===devId && s.cron_expr===cronExpr)` show "Same device already has identical cron — both will fire".

### List page (`schedules.tsx`)

- Columns: Device (`dev_name (dev_id)`), Hub, Cron (mono), Human, Payload `Badge`, Next run (`s.next_run_at` server else preview), Enabled `Switch`, Actions `Play/Pencil/Trash2`.
- Filters: `dev_id` `Select` (now includes AC+ATS) + `enabled` `Select`; URL search `validateSearch {dev_id, enabled}` stays.
- Polling `TIER2 6000` + `staleTime 30s` + `keepPreviousData`.
- Mutations optimistic (see D6); `run-now` toast "Queued to pending_commands" then invalidate; delete via `AlertDialog` (Destructive).
- RBAC: `isAdmin` guards `Switch`/`Play`/`Pencil`/`Trash2`; non-admin reads only with banner.

### A11y & polish

- `DialogTitle`/`Description` always present; `aria-invalid`, `aria-describedby="{id}-error"`, `data-invalid` for `border-destructive`, focus first invalid on submit.
- `prefers-reduced-motion` for spinners/switch.
- Reduced bundle: `sonner` + optional `cronstrue`; no `cron-parser` client side.

## API

- **Existing 7 suffice:** `GET /preview`, `POST /`, `GET /`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`, `POST /{id}/run-now` (`routers/schedules.py`). No change to `schedules` schema (`cron_expr 64`, `payload JSONB`, `tz`, `enabled`, `hub_id` auto).
- **Optional enhancement:** `GET /api/devices` add `dev_type?: "ATS"|"AC"|"ACC"|"TS"` query param — filter `query.filter(dev_table.dev_type==dev_type)` before `is_active`/`status` logic; add index if not present (already `dev_type` indexed via `dev_table`). If adopted, `dashboard/src/lib/api.ts:fetchDevices` gains `dev_type` arg and `queryKeys.devices.list(status, dev_type)`. Mark as `Phase 1.5` optional, not blocking.
- **Validation parity:** server `_validate_cron_expr` (5-field, no `@`, `CronTrigger.from_crontab`) + `_validate_payload` (`ATSCommand` xor `ACCommand`); client Zod mirrors `max 64`, `cronExprSchema`, `payloadSchema union refine >=1`, `tz ZoneInfo` (disabled input). Server is source of truth; client shows 422 toast.

## Frontend Changes File-by-File

| File | Action | Detail |
|------|--------|--------|
| `dashboard/src/routes/schedules.tsx` | **Modify** | Add `POLL_TIER2_ALERTS_MS` polling + jitter, `staleTime 30s`, `keepPreviousData`, optimistic `useMutation` for toggle/delete/run-now (`onMutate`/`onError`/`onSettled`), `sonner` toasts, `AlertDialog` for delete, include AC+ACC in device filter `Select`, render `Payload` badge per `dev_type`, overlap hint, fix `TableCell` hub null display. |
| `dashboard/src/components/schedules/ScheduleDialog.tsx` | **Refactor ? `ScheduleDialogV2.tsx` (or in-place)** | Replace raw cron `Input` + 4 pills with `CronBuilder`; replace single `atsDevices` prop with `devices` + derived `onlineATS/onlineAC/onlineACC`; add `PayloadForm` branching ATS vs AC; integrate server `previewScheduleCron` debounced; Zod `payloadSchema` union; `DialogTitle`/`Description` a11y (keep existing — already has it — verify `sr-only` if needed); `sonner` not `alert`; `hub_id` nullable/omitted. Keep `React.lazy` boundary. |
| `dashboard/src/components/schedules/CronBuilder.tsx` | **New** | `frequency` `Select`, `time` `Input type="time"`, weekday 7-chip `ToggleGroup`, `buildCron`/`parseCronToBuilderState` pure fns, raw `Collapsible` `Input`, preview via server. |
| `dashboard/src/components/schedules/PayloadForm/ATSForm.tsx` + `ACForm.tsx` | **New** | Controlled form sections; ATS checkboxes/radio, AC `target`/`action`/`temp`; presets mapping. |
| `dashboard/src/lib/cron.ts` | **Modify** | Add `buildCron`/`parseCronToBuilderState`; deprecate `getNextRuns` (keep exported for fallback/tests or guard `__LEGACY_CRON__`); optionally replace `describeCron` with `cronstrue` wrapper; keep `validateCron`/`parseField` for inline pre-validation before server call. |
| `dashboard/src/lib/scheduleApi.ts` | **Modify** | Fix `cronExprSchema` regex (allow `* , / -` correctly; currently `^[\d*,/\-\s]+$` rejects `*/5` trailing? keep but add `validateCron` refine); add `atsPayloadSchema`/`acPayloadSchema` Zod union `refine >=1`; export `buildCron` re-export; add `previewScheduleCron` typed wrapper if not using `api.ts` directly. |
| `dashboard/src/lib/api.ts` | **Modify** | `fetchDevices(status, dev_type?)` optional `dev_type` query param (gated on backend); `previewScheduleCron` already exists (`previewScheduleCron` in `api.ts:previewScheduleCron`) — ensure `tz` default `Asia/Jakarta`. |
| `dashboard/src/lib/queryKeys.ts` | **Modify** | Optionally overload `devices.list(status, dev_type?)`; keep `schedules.preview(cron,tz)` as is. |
| `dashboard/src/lib/constants.ts` | **No change** | Use existing `POLL_TIER2_*`/`STALE_TIER2_*`. |
| `dashboard/src/types/api.ts` | **Modify** | Ensure `ACCommand`/`ATSCommand`/`ScheduleCreate`/`SchedulePreviewResponse {human,next_runs,next_run}` match server `_to_response` (`human`, `next_run_at`, `next_runs`); add `DeviceResponse.status: "online"|"offline"|"pending"` already present. |
| `dashboard/package.json` | **Modify** | Add `sonner` (toast) + `cronstrue` (optional 6kB); no `cron-parser` client. |
| `server/app/routers/devices.py` | **Optional modify** | Add `dev_type` query param to `GET /api/devices` (`dev_type: Optional[str]=Query(None)`) with `WHERE dev_table.dev_type==dev_type.upper()` before other filters; add pytest. |

## Validation

- **Cron:** `cron_expr` 5-field, no `@`, max 64 ? `scheduler.py:_validate_cron_expr` via `CronTrigger.from_crontab(..., timezone=CANONICAL_TZ)`; client `cronExprSchema` + `validateCron` pre-check, server 422 ? toast; preview debounce 300ms.
- **Payload:** `router:_validate_payload` tries `ATSCommand` then `ACCommand` ? 422; client Zod `z.union([atsPayloadSchema.refine(>=1), acPayloadSchema])`; hub `main.py:validatePayload` re-validates before MQTT (defense in depth).
- **TZ:** canonical `Asia/Jakarta` everywhere (`CANONICAL_TZ`), `ZoneInfo(tz)` validation, stored `tz VARCHAR(64)`, display `toLocaleString("id-ID",{timeZone:"Asia/Jakarta"}) WIB` via `format.ts:formatWIB`; client TZ input disabled.
- **RBAC:** `require_role("admin")` on `POST/PATCH/DELETE/run-now` (`schedules.py:178,274,339,359`); `get_current_user` on reads/preview; `hub` path uses `X-Hub-Key` (`routers/commands.py`); frontend `isAdmin` disables writes and shows banner for `viewer`.

## Testing

- **Vitest (dashboard `src/__tests__`):** `buildCron`/`parseCronToBuilderState` round-trip for Daily/Weekdays/Weekly/Custom; `payloadSchema` union accepts `ATSCommand`/`ACCommand` and rejects empty/extra keys / bad `temp`; `CronBuilder` renders time/weekday chips and calls `onChange` with `"0 18 * * 0"` etc; `ScheduleDialogV2` shows `DialogTitle`, filters offline, branches payload.
- **Playwright (`dashboard/e2e`):** create Daily 18:00 warmup ? list shows `human`+`next_run`; edit to `AC1 24C`; toggle enabled optimistic; run-now ? toast "queued"; delete via `AlertDialog` ? removed; non-admin cannot see `New Schedule` (RBAC).
- **Pytest (`server/` if `dev_type` filter added):** `GET /api/devices?dev_type=ATS` returns only ATS; `?dev_type=AC` only AC; `?dev_type=bad` 400/422; existing `schedules` router tests unchanged (no new server file ? run existing `pytest server/ -k schedules`).
- **Lint/build:** `oxlint` 0 errors, `tsc -b && vite build` hidden sourcemap, `docker compose config` binds `127.0.0.1`.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cron drift client `UTC+7` vs server `ZoneInfo` | Med | Preview shows wrong next run; user schedules wrong minute | Server `/preview` is truth; debounce 300ms; keep client `getNextRuns` only as offline fallback with warning. |
| Payload validation parity (Zod vs Pydantic) | Med | Client allows submit that 422s | Zod union mirrors `ATSCommand`/`ACCommand` + server 422 toast; hub re-validates before publish. |
| Polling staleness (`false` today) | Med | Switch state stale | `TIER2 6000` + jitter + `staleTime 30s` + `onSettled invalidate` (optimistic covers interim). |
| Offline device scheduling | Med | Schedule fires, hub never ACKs, silent failure | Picker filters `online && is_active`; empty-state per type; warning toast if no online device. |
| Optimistic race (rapid toggle) | Low | Flicker / last-write-wins | `cancelQueries` + `setQueryData` + rollback fixes; `coalesce` on server still safe. |
| Overlap same `dev_id`+minute | Low | `manual+on` vs `auto` race | Non-blocking client hint; server intentionally allows (ops may want); document stagger. |
| `cronstrue`/`sonner` bundle | Low | +14kB | Measured; `ScheduleDialog` already `React.lazy`; no impact on critical path. |
| SQLite APScheduler memory vs PG `SQLAlchemyJobStore` | Low | Dev restart loses jobs before rehydrate | Documented in `server/AGENTS.md`; production PG is durable. |

## Migration / Rollout

1. Phase 1 ship behind same route (`/schedules`) — no URL change; keep old `ScheduleDialog` until V2 passes Playwright.
2. Preview debounce respects `30/min` rate limit.
3. Add `dev_type` server filter as backward-compat additive (no break).
4. Document AC presets (`20,24,26`) to align with `Controls.tsx` thresholds.
5. No firmware/hub deploy; verify `pending_commands` ? MQTT ? `<M,*>`/`<SGM,*>`/Gree IR in bench.

## Alternatives Considered

- Client `cron-parser` bundle vs server preview: server preview wins (authoritative, smaller bundle).
- Full `Calendar`/`Popover` date picker for cron: rejected for v1 — time + weekday chips suffice; `react-day-picker` already in deps but not needed for builder.
