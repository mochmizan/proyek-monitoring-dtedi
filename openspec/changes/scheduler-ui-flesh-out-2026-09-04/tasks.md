# Tasks: scheduler-ui-flesh-out-2026-09-04

> **Status:** proposed 2026-09-04 — backend-complete, frontend-partial ? production-grade Easy/Dynamic scheduler UI.

## 1. Scaffolding & deps

- [ ] 1.1 Verify `notes/research-scheduler-ui-2026-09-04.md` citations against `HEAD` (`server/app/routers/schedules.py:161-359`, `app/services/scheduler.py`, `dashboard/src/routes/schedules.tsx`, `components/schedules/ScheduleDialog.tsx`, `lib/cron.ts`, `lib/scheduleApi.ts`, `lib/queryKeys.ts`, `lib/constants.ts`)
- [ ] 1.2 Add `sonner` + `cronstrue` to `dashboard/package.json` (`npm i sonner cronstrue --save`); verify `npm run build` bundle delta <60kB and `React.lazy` still splits `ScheduleDialog`
- [ ] 1.3 Confirm shadcn `AlertDialog`/`Collapsible`/`ToggleGroup` primitives available (via `radix-ui`); add if missing (`npx shadcn add alert-dialog collapsible toggle-group`)

## 2. Phase 1 — Utils, types, schemas, API

- [ ] 2.1 `dashboard/src/lib/cron.ts` — add `buildCron({frequency: "daily"|"weekdays"|"weekly"|"custom", time: "HH:mm", weekdays: number[], raw?: string}) ? string` and `parseCronToBuilderState(cron) ? {frequency,time,weekdays,raw}`; keep `validateCron/parseField` for inline pre-check; deprecate `getNextRuns` (guard or keep for fallback/tests); optionally wrap `describeCron` with `cronstrue.toString(cron,{use24HourTimeFormat:true})`
- [ ] 2.2 `dashboard/src/lib/scheduleApi.ts` — fix `cronExprSchema` (relax to `z.string().trim().min(1).max(64)` + `refine(v=>v.split(/\s+/).length===5)` + `refine(!startsWith("@"))` + `refine(validateCron wrapper)`; remove bare regex `^[\d*,/\-\s]+$` that rejects edge cases); add `atsPayloadSchema`/`acPayloadSchema` mirroring `server/app/schemas.py:ATSCommand`/`ACCommand` (`mode/start_genset/reset >=1`, `target AC1|AC2, action ON|OFF|SET_TEMP, temp 16-30 required iff SET_TEMP`); export `payloadSchema = z.union([atsPayloadSchema, acPayloadSchema])` and `scheduleCreateSchema` update
- [ ] 2.3 `dashboard/src/types/api.ts` — verify `ACCommand`/`ATSCommand`/`ScheduleCreate`/`ScheduleResponse.human/next_run_at/next_runs`/`SchedulePreviewResponse.human/next_runs/next_run` match `server/app/routers/schedules.py:_to_response` and `preview_cron`; no drift
- [ ] 2.4 `dashboard/src/lib/api.ts` — extend `fetchDevices(status?, dev_type?)` to accept optional `dev_type?: "ATS"|"AC"|"ACC"|"TS"` and append `?dev_type=`; keep `previewScheduleCron(cronExpr, tz="Asia/Jakarta")` default; ensure `handleResponse` 422 surfaces `detail`
- [ ] 2.5 `dashboard/src/lib/queryKeys.ts` — optionally overload `devices.list(status, dev_type?) => [...all,"list",{status,dev_type}]` (backward-compat: existing call `list("all")` unchanged); keep `schedules.preview(cron,tz)` as is
- [ ] 2.6 `server/app/routers/devices.py` — **optional** add `dev_type: Optional[str]=Query(None)` to `GET /api/devices`, normalize `upper()`, filter `dev_table.dev_type==dev_type` before `is_active/status` branches; add 400 for invalid enum; add `pytest` case; mark optional — worker may skip if out of scope

## 3. Phase 2 — Dialog rebuild (CronBuilder + dynamic payload)

- [ ] 3.1 New `dashboard/src/components/schedules/CronBuilder.tsx` — `Select frequency`, `Input type="time"`, 7 weekday chips (`ToggleGroup` or `Button variant="outline"`), `buildCron` on change ? `onChange(cron_expr)`, raw `Collapsible` `Input` for `Custom`, preview panel (calls `previewScheduleCron` debounced 300ms via `useQuery` `enabled: validateCron(cron).valid`), shows `human` + `next_runs[0..2]` via `formatNextRun` ? `WIB`/`UTC`
- [ ] 3.2 New `dashboard/src/components/schedules/PayloadForm/ATSForm.tsx` — `mode` radio `auto/manual`, `start_genset` `on/off`, `reset rst`, bundled warmup shortcut; controlled via `value: ATSCommand` + `onChange`
- [ ] 3.3 New `dashboard/src/components/schedules/PayloadForm/ACForm.tsx` — `Select target AC1/AC2`, `Select action ON/OFF/SET_TEMP`, conditional `Input type="number" min=16 max=30` for `temp`; `zod` refine `temp` required iff `SET_TEMP`; controlled via `value: ACCommand`
- [ ] 3.4 `dashboard/src/components/schedules/ScheduleDialogV2.tsx` (or refactor `ScheduleDialog.tsx`) — props `{open, onOpenChange, editing: ScheduleResponse|null, devices: DeviceResponse[], onSuccess}`; derive `onlineATS/onlineAC/onlineACC` (`is_active && status==="online"`), tab/search, per-type empty states; `CronBuilder` + `PayloadForm` branching on `selectedDevice.dev_type`; server preview not client `getNextRuns`; Zod `payloadSchema` + `cronExprSchema` validation; `DialogTitle`/`Description` (even `sr-only`), `aria-invalid`/`aria-describedby`, focus first invalid; `hub_id` omitted (server resolves); `sonner` toasts; presets `PRESETS_ATS` + `PRESETS_AC` (AC1/AC2 x ON/OFF/SET 20/24/26)
- [ ] 3.5 Wire `ScheduleDialogV2` into `schedules.tsx` via existing `React.lazy` boundary; keep fallback until cutover; remove `atsDevices` prop contract

## 4. Phase 3 — List page polish + optimistic

- [ ] 4.1 `dashboard/src/routes/schedules.tsx` — list query `refetchInterval: POLL_TIER2_ALERTS_MS` (+ jitter via `refetchInterval: () => POLL_TIER2_ALERTS_MS * (1+(Math.random()-0.5)*0.3)` if helper), `staleTime: STALE_TIER2_ALERTS_MS`, `placeholderData: keepPreviousData`; include `AC`/`ACC` in device filter `Select` (not ATS-only); render payload `Badge` per `dev_type`
- [ ] 4.2 Optimistic `updateMut` (toggle enabled) — `onMutate: cancelQueries + getQueryData + setQueryData` ? `onError: rollback + toast.error(parseApiError)` ? `onSettled: invalidateQueries(schedules.all)`; apply same pattern to `deleteMut` and `runNowMut` (run-now: optimistic not needed, but toast + invalidate); replace all `alert()`/`confirm()` with `sonner` + `AlertDialog` (destructive variant for delete)
- [ ] 4.3 Overlap hint: `existingSchedules.some(s=>s.dev_id===devId && s.cron_expr===cronExpr)` non-blocking warning in dialog
- [ ] 4.4 Fix `formatNextRun` precedence: prefer `s.next_run_at` server, else preview; drop direct `getNextRuns` call from table cell
- [ ] 4.5 RBAC: `isAdmin` guards `Switch`/`Play`/`Pencil`/`Trash2`; viewer/operator sees reads + banner; ensure `useAuth` redirect matches `server/app/core/auth.py:require_admin`

## 5. Phase 4 — Tests + lint + build

- [ ] 5.1 Vitest `dashboard/src/__tests__/cronBuilder.test.ts` — `buildCron` daily `07:30?"30 7 * * *"`, weekdays `?"30 7 * * 1-5"`, weekly Sun `?"0 18 * * 0"`, weekly Mon/Thu `?"0 18 * * 1,4"`, `parseCronToBuilderState` round-trip, `*/30` custom
- [ ] 5.2 Vitest `dashboard/src/__tests__/payloadSchema.test.ts` — `atsPayloadSchema` accepts `{"mode":"manual","start_genset":"on"}` and rejects `{}`, `acPayloadSchema` accepts `{"target":"AC1","action":"SET_TEMP","temp":24}` and rejects `temp` missing/out-of-range/extra keys
- [ ] 5.3 Vitest `dashboard/src/__tests__/ScheduleDialogV2.test.tsx` — renders `DialogTitle`, filters offline, switches ATS?AC form, `cronstrue` human, `AlertDialog` on delete, focus first invalid
- [ ] 5.4 Playwright `dashboard/e2e/schedules.spec.ts` — seeded admin: create daily warmup (Builder) ? list shows human+next_run; edit to AC1 24C via AC form; toggle enabled optimistic; run-now toast; delete via AlertDialog; non-admin cannot see New Schedule
- [ ] 5.5 Pytest `server/tests/test_devices_devtype.py` — only if 2.6 shipped: `GET /api/devices?dev_type=ATS` only ATS, `?dev_type=AC` only AC, invalid 400; else skip
- [ ] 5.6 `npm run lint` 0 errors (oxlint, 20 fast-refresh warns allowed), `npm run build` `tsc -b && vite build` passes, `pytest server/ -q` 217+ pass, `docker compose config` still `127.0.0.1`

## 6. Docs & closeout (DOX pass)

- [ ] 6.1 Update `dashboard/AGENTS.md` — polling `TIER2` for schedules, `CronBuilder` + `PayloadForm` ownership, `sonner`/`cronstrue` deps
- [ ] 6.2 Update `wiki/index.md` + `wiki/scheduler.md` (or `wiki/schedules.md`) — visual builder, AC/ATS dynamic payload, server preview truth
- [ ] 6.3 Drop `notes/field-ops.md` line if AC scheduling unblocked, update `notes/benchmarks-baseline.md` if bundle measured
- [ ] 6.4 Refresh `openspec/changes/scheduler-ui-flesh-out-2026-09-04` status ? `implemented` / `completed` with commit SHA; archive per `openspec/AGENTS.md` lifecycle
- [ ] 6.5 `graphify update .` (optional; `graphify-out/` dirty after hooks is expected)
