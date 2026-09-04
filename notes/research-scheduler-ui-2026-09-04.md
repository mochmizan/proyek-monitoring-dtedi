# Research Brief: Scheduler UI — Production-Grade Synthesis

**Date:** 2026-09-04  
**Scope:** Server (HubGate V5) + Dashboard (Vite SPA) + Hub/Firmware delivery path  
**Goal:** Easy / Dynamic / Edit+Delete scheduler UX vs. current implementation  
**Type:** research synthesis — consolidates 3 parallel audits (Current Impl / Dashboard UX / Best Practice)

---

## 1. Executive Summary

The scheduler subsystem is **backend-complete but frontend-partial**.

- **Server** exposes 7 production-grade endpoints in `server/app/routers/schedules.py:161-359` with RBAC (admin-only writes), payload whitelisting via `ATSCommand`/`ACCommand`, 5-field cron validation via `CronTrigger.from_crontab` in `server/app/services/scheduler.py`, canonical `Asia/Jakarta` TZ enforcement via `ZoneInfo`, APScheduler `BackgroundScheduler` with `coalesce=True, max_instances=1, misfire_grace_time=60`, and `SQLAlchemyJobStore` (Postgres) vs memory+rehydrate (SQLite dev) — table `server/app/modelsv5.py:233` indexed on `(enabled, hub_id)` and `(enabled, dev_id)`, migration `alembic/b7c9e2f1a4d8`.
- **Dashboard** at `dashboard/src/routes/schedules.tsx` provides list/create/edit/delete/run-now but with an **ATS-only** preset model, raw cron `Input`, hardcoded TZ, client-side `getNextRuns` that uses a fixed UTC+7 offset (not `ZoneInfo`), no polling, and rough mutations (`alert()`/`confirm()`, invalidate-only, no optimistic update, no toast).
- **Hub/Firmware** path is intact: `hub/main.py` re-validates, derives `topic {hub_name}/{dev_type}/command`, polls `GET /api/hub/commands` every 2s; `firmware/PROMINI/PROMINI.ino` (`WDT 8S`, `VAC 210/190`, `WARMUP disabled`) and `firmware/WEMOS_AC/WEMOS_AC.ino` (Gree IR) consume the bundled payload correctly — warmup is server-authoritative via `pending_commands`.

**Gap to goal:**
- *Easy* — partially met (7 presets) but still requires raw cron comprehension; no visual builder.
- *Dynamic* — backend supports AC+ATS (`ACCommand` validated), frontend filters `atsDevices` only and has zero AC presets.
- *Edit/Delete* — present but not production-grade (no optimistic UI, no error boundary, no polling convergence).

**Recommendation:** Hide cron behind a visual builder (time + weekday + frequency → 5-field generation, raw collapsible), unify `cron-parser` + `cronstrue` + `ZoneInfo` parity, add AC preset matrix, implement TanStack optimistic mutations with toast, add `TIER2` polling, and filter device picker by `online && is_active && dev_type`.

---

## 2. Current State

### 2.1 Server — `server/app/routers/schedules.py` + `server/app/services/scheduler.py`

**Endpoints (7):**

| Method | Path | Line | Auth | Rate Limit | Purpose |
|---|---|---|---|---|---|
| `GET` | `/api/schedules/preview` | `server/app/routers/schedules.py:161` | auth | 60/min | Preview next N runs for a cron expr |
| `POST` | `/api/schedules` | `server/app/routers/schedules.py:178` | admin | 30/min | Create schedule |
| `GET` | `/api/schedules` | `server/app/routers/schedules.py:239` | auth (read) | 60/min | List (filters `dev_id`, `enabled`, `hub_id`) |
| `GET` | `/api/schedules/{id}` | `server/app/routers/schedules.py:260` | auth | 60/min | Detail |
| `PATCH` | `/api/schedules/{id}` | `server/app/routers/schedules.py:274` | admin | 30/min | Partial update (cron/payload/tz/enabled) |
| `DELETE` | `/api/schedules/{id}` | `server/app/routers/schedules.py:339` | admin | 30/min | Delete + remove APScheduler job |
| `POST` | `/api/schedules/{id}/run-now` | `server/app/routers/schedules.py:359` | admin | 30/min | Immediate dispatch (bypass cron) |

All mutating routes enforce RBAC via `require_admin` dependency; read routes allow `operator`/`viewer` per `server/app/core/config.py` RBAC matrix.

**Validation chain:**

- `ScheduleCreate` (`server/app/routers/schedules.py:178` + `server/app/schemas.py`) requires `dev_id: UUID`, `cron_expr: str` (max 64), `payload: dict` (non-empty), `tz: str = "Asia/Jakarta"`, `enabled: bool = True`. `hub_id` is **auto-resolved** from `devices.hub_id` — client never supplies it.
- `_validate_payload(payload)` (`server/app/routers/schedules.py:_validate_payload`) tries `ATSCommand(**payload)` then `ACCommand(**payload)`; if both fail → `422 Unprocessable Entity`. This is the **payload whitelist** — no freeform keys.
- `_validate_cron_expr(cron_expr)` (`server/app/services/scheduler.py:_validate_cron_expr`) rejects `@reboot`/`@daily` shortcuts, enforces exactly 5 fields, delegates to `CronTrigger.from_crontab(cron_expr, timezone=CANONICAL_TZ)` — canonical TZ constant `Asia/Jakarta`.
- TZ validated via `ZoneInfo(tz)` — invalid zone → `422`.

**Execution engine:**

- `APScheduler BackgroundScheduler` (`server/app/services/scheduler.py`) configured `JOB_DEFAULTS = {coalesce: True, max_instances: 1, misfire_grace_time: 60}` — prevents overlapping firings and coalesces missed runs within 60s window.
- Job store: `SQLAlchemyJobStore(engine)` when `DATABASE_URL` is Postgres; else in-memory + rehydration on boot (loads `schedules` rows where `enabled=True` and re-adds jobs). This matches the SQLite dev / Postgres prod duality documented in `server/AGENTS.md`.
- Job func `execute_scheduled_command(schedule_id)` inserts into `pending_commands` with `{"mode":"manual","start_genset":"on"}` style bundled payload — **bypass path** so hub treats scheduled commands identically to manual `POST /api/commands`.

**Persistence:**

- Table `schedules` (`server/app/modelsv5.py:233`): `id UUID PK`, `dev_id FK devices`, `hub_id FK hubs` (denormalized for index efficiency), `cron_expr VARCHAR(64)`, `payload JSONB`, `tz VARCHAR(64)`, `enabled BOOL`, `created_at/updated_at UTC`. Indexes `ix_schedules_enabled_hub (enabled, hub_id)` and `ix_schedules_enabled_dev (enabled, dev_id)` for list filtering.
- Alembic migration `alembic/versions/b7c9e2f1a4d8_add_schedules.py` creates table + indexes.

### 2.2 Dashboard — `dashboard/src/routes/schedules.tsx` + `dashboard/src/lib/*.ts`

**Route & data layer:**

- `dashboard/src/routes/schedules.tsx` — `createFileRoute("/schedules")` with Zod `validateSearch` `{dev_id?: string, enabled?: boolean}` (mirrors `device.$deviceId.tsx` / `room.$roomId.tsx` pattern). No polling (`refetchInterval: false`); list query `queryKeys.schedules.list(filters)` with `staleTime: 30s`.
- `dashboard/src/lib/api.ts:326-384` — re-exported by `dashboard/src/lib/scheduleApi.ts`: `fetchSchedules`, `fetchSchedule`, `createSchedule`, `updateSchedule`, `deleteSchedule`, `runScheduleNow`, `previewSchedule`. `scheduleApi.ts` is a thin re-export barrel (no logic duplication).
- `dashboard/src/lib/queryKeys.ts` — factory `queryKeys.schedules.{all, list, detail, preview}` consistent with `devices/rooms/alerts/commands` factories.
- `dashboard/src/lib/constants.ts` — 4-tier polling `TIER1 1500ms / TIER2 6000ms / TIER3 15000ms / TIER4 60000ms` with `±15% jitter`; schedules currently uses **no tier** (gap).

**Table & actions:**

- Columns: Device | Hub | Cron | Human | Payload | Next run | Enabled | Actions. Human via `s.human ?? describeCron(s.cron_expr)` — `describeCron` in `dashboard/src/lib/cron.ts:describeCron` only handles 3 exact strings, falls back to raw cron.
- Next run: `s.next_run_at` (server-computed, `Asia/Jakarta`) else client `getNextRuns(cron_expr, 1)[0]` — client uses brute-force minute iteration with hardcoded `UTC+7` offset, not `ZoneInfo`.
- Payload rendered as `Badge` (`JSON.stringify` truncated).
- Actions: `Switch` (toggle `enabled` via `PATCH`), `Play` (run-now), `Pencil` (edit → opens `ScheduleDialog`), `Trash2` (delete via `confirm()`), all using `alert()`/`confirm()` and `queryClient.invalidateQueries` only (no optimistic).

**ScheduleDialog — `dashboard/src/components/ScheduleDialog.tsx` (lazy-loaded via `React.lazy`):**

- 7 `PRESETS: Record<string, {label, cron, payload}>` — **all ATS**: warmup bundled `{"mode":"manual","start_genset":"on"}`, `{"mode":"auto"}`, `{"start_genset":"off"}`, `{"reset":"rst"}` variants etc. **No AC presets** despite `ACCommand` backend support.
- Controls: raw `Input` for `cron_expr` + 4 quick-pill buttons (`Every 5m`, `Hourly`, `Daily 18:00`, `Weekly Sun 18:00`), `Select` for device (populated by `atsDevices` prop — filtered caller-side), `Switch` for enabled, `Input` for TZ (hardcoded `Asia/Jakarta`, disabled), payload `Select` mirroring presets.
- Validation: `cronExprSchema` (Zod regex `^[\d\*\/\,\-\s]+$`) in `scheduleApi.ts` rejects letters — blocks `@daily` already rejected server-side but also blocks valid `*` combos silently. `validateCron` from `cron.ts:parseField/validateCron` mirrors server 5-field check client-side.
- `openspec/changes/ats-flexible-schedule-2026-08-29/spec.md` intended `cron-parser` + `cronstrue` + `Calendar`/`Popover` but implementation diverged to custom `cron.ts` parser.

### 2.3 Hub / Firmware — `hub/main.py` + `firmware/*`

- `hub/main.py` — polls `GET /api/hub/commands?hub_id=...` every `2s`, derives MQTT topic `f"{hub_name}/{dev_type}/command"` dynamically (`dev_type` from `devices.dev_type`). Re-validates payload against same `ATSCommand`/`ACCommand` schemas before publish — defense in depth. WAL `MAX_PENDING_ROWS=20000` with `0.35s` pacing and `_hub_created_at` epoch injection on replay preserves capture time across offline bursts (`hub/AGENTS.md`).
- `firmware/PROMINI/PROMINI.ino` — Pro Mini FSM **canonical** (`WDT 8S`, `MCUSR` boot cause, `VAC 210/190` hysteresis, `SIZE 20/60`, `RST exact`, `MAX 3` retries, `WARMUP disabled` — server `schedules` authoritative, `<M,auto>` `<T,unixtime>` `<RTC_OK>` framing, `proofed dcfeb84`).
- `firmware/WEMOS_ATS/WEMOS_ATS.ino` — ATS bridge canonical (`HUB_NAME`/`DEV_TYPE: ATS`, 512B buf, bounded serial, backoff).
- `firmware/WEMOS_AC/WEMOS_AC.ino` — AC/IR 2x Gree, dual I2C, EEPROM `0xAC` 8B/unit, consumes `ACCommand` payload (`target: AC1/AC2`, `action: ON/OFF/SET_TEMP`, `temp 16-30`).
- Field note: pre-`dcfeb84` firmware re-latches `EMERGENCY_GENSET` after `RST` when warmup overdue + genset disconnected — `RST` alone cannot clear; requires flash of canonical `PROMINI` + `WEMOS_ATS`.

---

## 3. Device Dynamics

**How hub resolves `dev_id` → topic:**

1. Dashboard sends `POST /api/schedules {dev_id, cron_expr, payload, tz}` — no `hub_id` (`server/app/routers/schedules.py:178`).
2. Server resolves `device = db.get(Device, dev_id)` → `hub_id = device.hub_id`, stores both on `schedules` row (`server/app/modelsv5.py:233`).
3. APScheduler fires → `pending_commands` row with `hub_id`, `dev_id`, `payload` (`server/app/services/scheduler.py:execute_scheduled_command`).
4. Hub polls `GET /api/hub/commands?hub_id=X` (`hub/main.py:hubPollLoop` every 2s) → receives `pending_commands` batch → for each, looks up `hub_name` + `dev_type` → publishes to `{hub_name}/{dev_type}/command` with `payload` JSON.

**Payload binding:**

- `ATSCommand` (`server/app/schemas.py:ATSCommand`): `mode?: "auto"|"manual"`, `start_genset?: "on"|"off"`, `reset?: "rst"` — requires **≥1 field** (`model_validator`). Bundled warmup is `{"mode":"manual","start_genset":"on"}` — atomic bypass.
- `ACCommand` (`server/app/schemas.py:ACCommand`): `target: "AC1"|"AC2"`, `action: "ON"|"OFF"|"SET_TEMP"`, `temp?: int 16-30` (required iff `SET_TEMP`).

**Device discovery gaps:**

- `GET /api/devices?status=pending|active|all` (`server/app/routers/devices.py:GET /api/devices`) supports dual auth (user session or `X-Hub-Key`) but has **no `dev_type` filter** — frontend filters `devices.filter(d => d.dev_type==="ATS")` client-side. Same for AC.
- Picker in `ScheduleDialog` receives `atsDevices` prop (caller-filtered) — shows **offline/disabled** devices equally; no `is_active && status==="online"` guard.
- `useCommandLifecycle` (`dashboard/src/hooks/useCommandLifecycle.ts`) polls `GET /api/commands/{id}` tier1 `1500ms`, timeout `12000ms`, auto-dismiss `8000ms`, invalidates `devices/rooms/alerts` — schedule mutations do **not** invalidate this path (different domain), but should invalidate `queryKeys.schedules`.

**Polling tiers (from `dashboard/src/lib/constants.ts`):**

- `TIER1 1500ms` — command lifecycle, device detail optimistic.
- `TIER2 6000ms` — room maps, device history, alerts pagination.
- `TIER3 15000ms` — ATS HistoryChart 6h/24h.
- `TIER4 60000ms` — background idle warmup (route preload).
- Schedules list should use `TIER2` (6000ms) — currently `false` (manual refresh only).

---

## 4. UX Gaps vs Goal

| Goal | Spec (openspec) | Current | Gap | Severity |
|---|---|---|---|---|
| **Easy** | Visual cron builder: `Calendar` + `Popover` + `Select` for time/weekday/frequency, `cron-parser` + `cronstrue` humanization, server `/preview` for next runs | Raw `Input` + 4 quick-pills, custom `cron.ts` brute-force `UTC+7`, `describeCron` 3 strings, server preview never called | User must understand 5-field cron; TZ fragile; human text useless for most expressions; next-run may drift vs server | **High** |
| **Dynamic** | Device picker dynamic by `dev_type`, payload form adapts to `ATSCommand` vs `ACCommand`, AC presets (ON/OFF/SET_TEMP) | `PRESETS` 7x ATS-only, `atsDevices` filtered prop, no AC presets, payload `Select` hardcoded ATS | AC scheduling **backend-ready but UI-invisible**; cannot schedule AC without hand-crafting JSON | **High** |
| **Edit+Delete** | Optimistic toggle, inline edit dialog, delete with confirmation variant, toast feedback, polling convergence | `Switch` + `Pencil` + `Trash2` present but `confirm()`/`alert()`, `invalidateQueries` only, no `onMutate`/`onError` rollback, no polling, no `DialogTitle`/`Description` a11y | Feels unpolished; race on rapid toggle; no error recovery; a11y violation (missing DialogTitle) | **Medium** |
| **Preview fidelity** | `GET /preview` server-authoritative, `ZoneInfo Asia/Jakarta` | Client `getNextRuns` with `+7h` offset, `cronExprSchema` regex rejects valid, `validateCron` custom | Client preview diverges from server on DST-adjacent edge, and on `*/n`/`1-5` combos the custom parser mishandles | **Medium** |
| **Device targeting** | Filtered picker: `dev_type` x `is_active` x `online`, search, empty state per type | Unfiltered `atsDevices`, shows offline/disabled, no search, generic empty `No ATS found` | User can schedule against offline device; silent failure until APScheduler fires and hub never ACKs | **Medium** |
| **Validation parity** | Zod parity with server Pydantic, max 64, non-empty payload, TZ canonical | `cronExprSchema` regex blocks letters (redundant), no payload `>=1 field` client check, TZ input disabled but not validated | Client allows submit that server 422s (e.g. empty payload) — wasted round-trip | **Low** |

**Additional UX debts:**

- `room.$roomId.tsx` / `device.$deviceId.tsx` use hand-rolled modal in some places vs `shadcn Dialog` in schedules — inconsistency (`dashboard/src/routes/room.$roomId.tsx`, `dashboard/src/routes/device.$deviceId.tsx`).
- `ScheduleDialog` missing `DialogTitle` + `DialogDescription` — fails `shadcn` a11y contract (`dashboard/src/components/ui/dialog.tsx`).
- No overlap/collision detection (two schedules same `dev_id` + overlapping cron) — backend allows it; UI does not warn.
- No reduced-motion audit for polling spinners / switch transitions.

---

## 5. Best Practice Recommendations

### 5.1 Hide Cron — Visual Builder (primary recommendation)

**Why:** Raw cron is the #1 usability barrier; openspec intended to abstract it. Best practice per `cron-parser` + `cronstrue` docs is to **generate** cron from UI state, not parse user-typed cron.

**Pattern:**

- Frequency `Select`: `Daily | Weekdays (Mon-Fri) | Weekly | Custom`
- Time picker: `Input type="time"` or `Popover` + `Calendar`-style hour/minute `Select` (24h `WIB`) — value `HH:mm`.
- Weekday multi-select: `ToggleGroup` / 7 `Button variant="outline"` chips (`Mon..Sun`) — maps to 5th field.
- Generator: `buildCron({frequency, time, weekdays}) → "m H * * dow"` — e.g. `Daily 18:00 → "0 18 * * *"`; `Weekdays 07:30 → "30 7 * * 1-5"`; `Weekly Sun 18:00 → "0 18 * * 0"`.
- Raw collapsible: `Collapsible` / `Details` with `Input` bound to same `cron_expr` for power users — validates via server `GET /preview` debounce (300ms).
- Human: `cronstrue.toString(cron, {locale:"en", use24HourTimeFormat:true})` + server `next_run_at` — **remove** custom `describeCron`/`getNextRuns` or keep as fallback only.

**Files:** new `dashboard/src/components/schedule/CronBuilder.tsx`, `dashboard/src/lib/cron.ts` to re-export `cronstrue` + `cron-parser` (or keep server preview as source of truth).

### 5.2 shadcn + a11y Compliance

- `ScheduleDialog` must render `DialogTitle` + `DialogDescription` (even `sr-only`) per `dashboard/src/components/ui/dialog.tsx` contract — `aria-labelledby`/`aria-describedby` required.
- Inputs: `aria-invalid={!!error}`, `aria-describedby="{id}-error"`, `data-invalid` for Tailwind `data-[invalid]:border-destructive`, focus first invalid on submit (`useRef` + `focus()`).
- Use `FormControl` pattern from `shadcn` form (or manual `Label` + `Input` + `p id="{id}-error"`).

### 5.3 TanStack Query — Optimistic Mutations + Toast

Replace `invalidate-only + alert()` with:

```ts
useMutation({
  mutationFn: (vars) => updateSchedule(vars),
  onMutate: async (vars) => {
    await queryClient.cancelQueries({ queryKey: queryKeys.schedules.list() });
    const prev = queryClient.getQueryData(queryKeys.schedules.list(filters));
    queryClient.setQueryData(queryKeys.schedules.list(filters), (old) =>
      old?.map(s => s.id===vars.id ? {...s, ...vars.patch} : s)
    );
    return { prev };
  },
  onError: (err, vars, ctx) => {
    queryClient.setQueryData(queryKeys.schedules.list(filters), ctx.prev);
    toast.error(parseApiError(err));
  },
  onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all }),
});
```

- Use `sonner` / existing `toast` (not `alert`/`confirm`); delete uses `AlertDialog` variant.
- Invalidate `queryKeys.schedules.all` on settle; also invalidate `queryKeys.devices.detail(devId)` if schedule affects device dot.

### 5.4 Polling & Cache

- List: `refetchInterval: TIER2` (`6000ms`) with `TIER2` jitter — matches `room.$roomId.tsx` map polling. Keeps badge/switch state convergent without manual refresh.
- Detail/preview: `staleTime: 30s`, `refetchOnWindowFocus: true` (already present).
- Keep `keepPreviousData` placeholder for filter toggles (`enabled`/`dev_id`).

### 5.5 Dynamic Device & Payload Forms

- Picker query: `useQuery({ queryKey: queryKeys.devices.list({status:"active"}), queryFn: () => fetchDevices({status:"active"}) })` then client-derive `atsDevices = devices.filter(d => d.dev_type==="ATS" && d.is_active && d.status==="online")` and `acDevices` similarly — add `dev_type` server filter when `server/app/routers/devices.py:GET /api/devices` gains it (trivial `?dev_type=ATS|AC`).
- Presets mirroring: split `PRESETS_ATS` (existing 7) + `PRESETS_AC` (`AC1 ON`, `AC1 OFF`, `AC1 SET 24C`, `AC2` variants) — payload `Select` options switch on `selectedDevice.dev_type`.
- Payload form adapts: `dev_type==="ATS"` → `mode`/`start_genset`/`reset` checkboxes; `dev_type==="AC"` → `target` `Select` + `action` `Select` + conditional `temp` `Input type="number" min=16 max=30`.
- Zod parity: `payloadSchema = z.union([atsPayloadSchema.refine(v=>Object.keys(v).length>=1), acPayloadSchema])` with `max_length 64` on `cron_expr`.

### 5.6 Other

- Overlap hint: client warns if `existingSchedules.some(s => s.dev_id===newDevId && s.cron_expr===newCron)` — non-blocking.
- Reduced-motion: respect `prefers-reduced-motion` for switch/polling spinners.

---

## 6. Payload Contracts

### 6.1 ATS — `server/app/schemas.py:ATSCommand`

```ts
// ATSCommand — at least one key required
type ATSCommand = {
  mode?: "auto" | "manual";
  start_genset?: "on" | "off";
  reset?: "rst";
} // & { [k: string]: never } — no extra keys
```

- **Warmup bundled (canonical):** `{"mode":"manual","start_genset":"on"}` — hub treats as bypass `pending_commands` `mode:manual` (server `scheduler.py:execute_scheduled_command`).
- **Auto restore:** `{"mode":"auto"}`.
- **Genset off:** `{"start_genset":"off"}` (often combined with `mode`).
- **Reset:** `{"reset":"rst"}` — maps to `<RST,rst>` framing on `PROMINI` serial (`firmware/PROMINI/PROMINI.ino:RST exact`).
- Server `_validate_payload` tries `ATSCommand` first; hub re-validates before `MQTT publish` (`hub/main.py:validatePayload`).

### 6.2 AC — `server/app/schemas.py:ACCommand`

```ts
type ACCommand = {
  target: "AC1" | "AC2";
  action: "ON" | "OFF" | "SET_TEMP";
  temp?: number; // 16..30, required iff action==="SET_TEMP"
}
```

- `WEMOS_AC` consumes via Gree IR (`firmware/WEMOS_AC/WEMOS_AC.ino`); `target` selects unit, `action` drives IR code, `temp` only for `SET_TEMP`.
- Dashboard currently has **zero** AC presets — add matrix:
  - `AC1 ON` → `{"target":"AC1","action":"ON"}`
  - `AC1 OFF` → `{"target":"AC1","action":"OFF"}`
  - `AC1 24C` → `{"target":"AC1","action":"SET_TEMP","temp":24}` (and `AC2` variants).

### 6.3 Validation Matrix

| Field | Server (Pydantic) | Client (Zod) | Hub (re-validate) |
|---|---|---|---|
| `dev_id` | `UUID`, FK exists, `hub_id` auto | `z.string().uuid()` | — (hub_id derived) |
| `cron_expr` | 5-field, `CronTrigger.from_crontab`, no `@`, max 64 | `cronExprSchema` regex + `validateCron` | — |
| `payload` | `ATSCommand` xor `ACCommand`, non-empty | `payloadSchema` union + `>=1` refine | `validatePayload` same |
| `tz` | `ZoneInfo`, default `Asia/Jakarta` | disabled `Input` `Asia/Jakarta` | — (stored UTC, display WIB) |
| `enabled` | `bool` | `Switch` | — |

---

## 7. TZ / RBAC / Validation

### 7.1 Timezone

- **Canonical TZ:** `CANONICAL_TZ = ZoneInfo("Asia/Jakarta")` (`server/app/services/scheduler.py:CANONICAL_TZ`, `server/app/core/config.py:CANONICAL_TZ`). All cron evaluation is TZ-aware via `CronTrigger(..., timezone=CANONICAL_TZ)`.
- **Storage:** `schedules.cron_expr` stored as written; `next_run_at` computed server-side in `Asia/Jakarta` then serialized UTC (`server/app/routers/schedules.py:GET /preview` returns `next_runs: list[datetime]` UTC).
- **Display:** Dashboard renders via `toLocaleString("id-ID", {timeZone:"Asia/Jakarta"})` → `WIB` suffix (`dashboard/src/lib/format.ts:formatWIB`). WAL replay `_hub_created_at` epoch preserves capture time (`hub/main.py:WAL`).
- **Fragility:** Client `getNextRuns` in `dashboard/src/lib/cron.ts:getNextRuns` adds fixed `+7h` offset, not `ZoneInfo` — diverges from server if `Asia/Jakarta` ever observes DST (historical) or on date-boundary edge. **Fix:** call `GET /api/schedules/preview?cron_expr=...&tz=Asia/Jakarta` (server-authoritative) debounced, or import `cron-parser` with `tz: "Asia/Jakarta"` (`cron-parser` `tz` option uses `Intl`/`luxon`).

### 7.2 RBAC

- Writes (`POST`, `PATCH`, `DELETE`, `run-now`) → `require_admin` (`server/app/routers/schedules.py:178,274,339,359` via `server/app/core/auth.py:require_admin`).
- Reads (`GET /`, `GET /{id}`, `GET /preview`) → `get_current_user` (any authenticated `operator`/`viewer`/`admin`).
- Hub polling `GET /api/hub/commands` → `X-Hub-Key` header (`server/app/routers/commands.py:GET /api/hub/commands`), not user session.
- Frontend guards: `schedules.tsx` `useAuth` check redirects non-admin away from mutating actions; `Switch`/`Play`/`Pencil`/`Trash2` disabled if `user.role!=="admin"`.

### 7.3 Validation & Rate Limits

- `cron_expr` max 64, `payload` non-empty dict, `tz` `ZoneInfo` — all `422` on violation (`server/app/routers/schedules.py:_validate_cron_expr`, `_validate_payload`).
- Rate limits via `SlowAPI` (`server/app/core/config.py:limiter`): `30/min` for writes, `60/min` for reads/preview — keyed by `X-Real-IP`/`X-Forwarded-For` `parts[0]`.
- Client `cronExprSchema` (`dashboard/src/lib/scheduleApi.ts:cronExprSchema`) regex `^[\d\*\/\,\-\s]+$` rejects letters — redundant with server but blocks valid `*` combos with trailing spaces; should be relaxed to `z.string().max(64).refine(validateCron)`.

---

## 8. Risks & Open Questions

### Risks

1. **Preview divergence (Medium):** Client `UTC+7` vs server `ZoneInfo` — next-run shown in dialog may differ from actual fire time by hours on boundary days. Mitigate by making `GET /preview` the source of truth.
2. **AC scheduling invisible (Medium):** Backend supports AC but UI does not expose it — feature appears missing to operators; risk of manual `curl` workarounds with malformed payloads.
3. **Offline device scheduling (Medium):** Picker allows offline/disabled devices — schedule fires, hub never ACKs, device stays stale; no feedback loop. Need `online && is_active` filter + empty-state per type.
4. **No overlap detection (Low):** Two schedules same `dev_id` + same minute (e.g. `0 18 * * *` and `0 18 * * 0`) both fire — APScheduler `coalesce` only dedupes same job, not cross-job. Could cause `MANUAL ON` + `AUTO` race.
5. **Optimistic race (Low):** Rapid toggle without `onMutate` cancel can interleave `PATCH` requests — last-write-wins but UI flickers. Optimistic with `cancelQueries` fixes.
6. **SQLite job store (Low):** Dev/edge uses in-memory APScheduler + rehydrate — jobs lost if process restarts before rehydrate completes. Production Postgres `SQLAlchemyJobStore` is durable; dev gap acceptable but document.
7. **WAL replay ordering (Low):** `hub/main.py` WAL `0.35s` pacing with `_hub_created_at` preserves capture time, but scheduled `pending_commands` inserted with `now_utc` — replay vs live ordering is correct (both UTC) but worth verifying `event_time` precedence in `alert_engine`.

### Open Questions

1. **Server `GET /api/devices?dev_type=` filter:** Should `server/app/routers/devices.py:GET /api/devices` add `dev_type` query param to avoid client-side filtering? Trivial `WHERE dev_type=:t` — propose in next PR.
2. **Cron builder scope:** Daily/Weekdays/Weekly covers 95% of warmup use cases — does product need `Custom` freeform (with `CronBuilder` + raw collapsible) or is constrained builder sufficient?
3. **AC preset temps:** What default `SET_TEMP` values should presets offer (e.g. `20, 24, 26`)? Align with `Controls.tsx` inverter thresholds (`warn<crit`).
4. **Schedule history/audit:** Should `schedules` have `last_run_at`/`last_status`/`run_count` columns for observability, or is `pending_commands` + `device_events` sufficient?
5. **Overlap policy:** Should server reject overlapping schedules same `dev_id` + same effective minute, or only warn client-side?
6. **`cron-parser` vs server preview:** Prefer server preview (authoritative, no bundle cost) or bundle `cron-parser` (offline preview, but adds ~15kB)? Recommend server preview + `cronstrue` for human text (no `cron-parser` bundle).

---

## 9. Sources

### Server

- `server/app/routers/schedules.py:161` — `GET /preview`
- `server/app/routers/schedules.py:178` — `POST /` create (admin, 30/min, `_validate_payload`, `_validate_cron_expr`)
- `server/app/routers/schedules.py:239` — `GET /` list (filters `dev_id`/`enabled`/`hub_id`)
- `server/app/routers/schedules.py:260` — `GET /{id}` detail
- `server/app/routers/schedules.py:274` — `PATCH /{id}` (admin)
- `server/app/routers/schedules.py:339` — `DELETE /{id}` (admin)
- `server/app/routers/schedules.py:359` — `POST /{id}/run-now` (admin)
- `server/app/services/scheduler.py:_validate_cron_expr` — 5-field, no `@`, `CronTrigger.from_crontab` with `CANONICAL_TZ`
- `server/app/services/scheduler.py:CANONICAL_TZ` — `ZoneInfo("Asia/Jakarta")`
- `server/app/services/scheduler.py:JOB_DEFAULTS` — `coalesce=True, max_instances=1, misfire_grace_time=60`
- `server/app/services/scheduler.py:execute_scheduled_command` — inserts `pending_commands` bundled bypass
- `server/app/modelsv5.py:233` — `schedules` table + `ix_schedules_enabled_hub` / `ix_schedules_enabled_dev`
- `server/app/schemas.py:ATSCommand` — `mode/start_genset/reset` >=1
- `server/app/schemas.py:ACCommand` — `target AC1/AC2, action ON/OFF/SET_TEMP, temp 16-30`
- `server/app/routers/devices.py:GET /api/devices` — `?status` dual auth, no `dev_type` filter
- `server/app/routers/commands.py:GET /api/hub/commands` — hub polling every 2s, `X-Hub-Key`
- `server/app/routers/commands.py:POST /api/commands` — validates with `db/dev_id` context
- `server/app/core/config.py:CANONICAL_TZ` / `limiter` — TZ constant, SlowAPI 30/60 per min via `X-Real-IP`
- `server/app/core/auth.py:require_admin` — RBAC admin-only writes
- `alembic/versions/b7c9e2f1a4d8_add_schedules.py` — schedules migration
- `server/AGENTS.md` — `SQLAlchemyJobStore` Postgres vs memory+rehydrate SQLite, `pool_size` etc

### Dashboard

- `dashboard/src/routes/schedules.tsx` — route `createFileRoute("/schedules")`, `validateSearch {dev_id, enabled}`, Table, no polling, `describeCron`/`getNextRuns` fallback, `Switch`/`Play`/`Pencil`/`Trash2` with `alert`/`confirm`
- `dashboard/src/routes/device.$deviceId.tsx` — `validateSearch {range}`, decoupled detail `staleTime 300s`, `useDeviceHistory`, `canonicalDevId`
- `dashboard/src/routes/room.$roomId.tsx` — same search pattern, map polling `TIER2`, `keepPreviousData`
- `dashboard/src/components/ScheduleDialog.tsx` — `React.lazy`, `PRESETS` 7 ATS-only, raw `Input` + 4 quick-pills, hardcoded `Asia/Jakarta`, `atsDevices` prop
- `dashboard/src/lib/api.ts:326-384` — `fetchSchedules/fetchSchedule/createSchedule/updateSchedule/deleteSchedule/runScheduleNow/previewSchedule`
- `dashboard/src/lib/scheduleApi.ts` — re-export barrel + `cronExprSchema` regex
- `dashboard/src/lib/queryKeys.ts` — `queryKeys.schedules.{all,list,detail,preview}` factory
- `dashboard/src/lib/constants.ts` — `TIER1 1500 / TIER2 6000 / TIER3 15000 / TIER4 60000` + `±15% jitter`
- `dashboard/src/lib/cron.ts:parseField` / `validateCron` / `describeCron` / `getNextRuns` — custom parser, 3-string human, brute-force `UTC+7`
- `dashboard/src/lib/format.ts:formatWIB` — `toLocaleString id-ID Asia/Jakarta WIB`
- `dashboard/src/components/ui/dialog.tsx` — `DialogTitle`/`Description` a11y contract
- `dashboard/src/components/ui/badge.tsx` / `button.tsx` / `card.tsx` / `input.tsx` / `label.tsx` / `pagination.tsx` / `select.tsx` / `switch.tsx` / `table.tsx` / `tooltip.tsx` — 12 shadcn components
- `dashboard/src/hooks/useCommandLifecycle.ts` — `TIER1 1500` polling, `12000` timeout, `8000` auto-dismiss, invalidates `devices/rooms/alerts`
- `dashboard/AGENTS.md` — `POLL_MS`, `STALE_MS`, `keepPreviousData`, `Route.useSearch`, `React.lazy ScheduleDialog`

### Hub / Firmware

- `hub/main.py:hubPollLoop` — `GET /api/hub/commands` every 2s, topic `{hub_name}/{dev_type}/command`, re-validate `ATSCommand`/`ACCommand`
- `hub/main.py:WAL` — `MAX_PENDING_ROWS=20000`, `0.35s` pacing, `_hub_created_at` epoch injection
- `hub/AGENTS.md` — WAL FIFO, whitelist sync, dynamic topic
- `firmware/PROMINI/PROMINI.ino` — `WDT 8S`, `MCUSR`, `VAC 210/190`, `SIZE 20/60`, `RST exact`, `MAX 3`, `WARMUP disabled`, `<M,auto>` framing
- `firmware/WEMOS_ATS/WEMOS_ATS.ino` — `HUB_NAME`/`DEV_TYPE: ATS`, 512B buf, `RTC_OK`, `proofed dcfeb84`
- `firmware/WEMOS_AC/WEMOS_AC.ino` — dual I2C, EEPROM `0xAC`, Gree IR 2x, `ACCommand` consumer

### Spec & Design

- `openspec/changes/ats-flexible-schedule-2026-08-29/spec.md` — intended `cron-parser` + `cronstrue` + `Calendar`/`Popover`, diverged to custom `cron.ts`
- `openspec/changes/ats-flexible-schedule-2026-08-29/proposal.md` — flexible cron `Asia/Jakarta` server-authoritative warmup
- `docs/2026-07-01-iot-temperature-monitoring-design.md` — stack, `pending_commands` bypass, `Asia/Jakarta` canonical
- `AGENTS.md` — global `CANONICAL_TZ`, `schedules` table `cron_expr/payload/tz/enabled`, `V5` suffix, `WARMUP disabled` `2026-08-31`

### External Best Practice (Context7 / docs)

- `cron-parser` — `tz`/`strict` options, `CronExpressionParser.parse(cron, {tz:"Asia/Jakarta"})`
- `cronstrue` — `toString(cron, {locale:"en", use24HourTimeFormat:true})` humanization
- `shadcn/ui Dialog` — requires `DialogTitle` + `DialogDescription` for `aria-labelledby`/`aria-describedby`, `data-invalid` + `aria-invalid`
- `TanStack Query` — `onMutate`/`onError`/`onSettled` optimistic pattern with `cancelQueries` + `setQueryData` + rollback + `toast`
- `APScheduler` — `BackgroundScheduler`, `SQLAlchemyJobStore`, `CronTrigger.from_crontab`, `coalesce`/`misfire_grace_time`

---

*Generated 2026-09-04 — synthesis of 3 researcher audits; verify citations against current `HEAD` before implementation.*
