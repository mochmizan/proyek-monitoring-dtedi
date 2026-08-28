# Proposal: ATS Flexible Scheduling + Shard Tech Stack Decisions

## Summary

Add server-authoritative flexible cron scheduling for ATS genset warmup (and future device commands) via dashboard, plus shadcn-based UI upgrade. Replaces the PROMINI firmware weekly Sunday 18:00 RTC trigger with VPS APScheduler-driven `pending_commands` injection, enabling per-device/per-hub cron expressions, timezone-correct execution, and bundled payloads that bypass the ATS `check_genset_mode` guard. Decides shard tech-stack questions raised by researchers: shadcn ADD, Redis/SSE/Convex DEFER/REJECT, single-VPS scheduler ADD.

## Motivation

### RTC drift — why firmware scheduling is insufficient

- **Current:** `firmware/PROMINI/PROMINI.ino` + `firmware/fsm_w_serial/fsm_w_serial.ino` use DS3231 RTC to fire a hardcoded weekly warmup every Sunday 18:00 (`check_genset_mode` guard).
- **Problems:**
  - DS3231 drifts 1-2 min/month without NTP; no correction path on PROMINI (no WiFi). Schedule silently skews.
  - Hardcoded cron — changing day/time requires reflash via ISP/USB on every PROMINI. No dashboard control, no per-device variance.
  - `check_genset_mode == manual` blocks `start_genset:on`; RTC path cannot force manual override, so warmup is skipped if operator left genset in manual.
  - No audit trail, no RBAC, no enable/disable without firmware edit. No DST/Asia/Jakarta handling — RTC runs in local time but VPS interprets UTC.
- **Goal:** Move scheduling authority to VPS (single source of truth, NTP-synced), keep ESP/PROMINI as dumb executors via existing `pending_commands` poll (2s hub interval).

### Why flexible cron (not weekly enum)

- Researchers + ops need: daily test pulse, twice-weekly warmup, monthly load-bank, and per-hub staggered windows to avoid campus-wide genset load spike.
- Cron expression (`cron-parser` + `cronstrue` for preview) covers all without schema churn. Dashboard uses shadcn `Calendar`/`Select`/`Popover` to build cron without hand-editing.

## What Changes

- **Server scheduler:** New `schedules` domain table + APScheduler 3.x `BackgroundScheduler` with `SQLAlchemyJobStore` (+ `lifespan` manager) that triggers `pending_commands` inserts at cron moments.
- **API:** CRUD `POST/GET/PATCH/DELETE /api/schedules` (admin-only write, RBAC), cron validation via `cron-parser`, human preview via `cronstrue`, timezone `Asia/Jakarta` canonical.
- **Dashboard:** New Scheduling view/route using shadcn primitives (`Dialog`, `Select`, `Calendar`, `Popover`, `Table`) to create/edit/enable schedules with command `Select` (SGM on/off, RST, mode) and cron builder.
- **Firmware contract:** Scheduler payload is bundled `{mode:manual, start_genset:on}` (JSON) so ATS relay bypasses `check_genset_mode` guard — firmware already accepts JSON command batch.
- **Hub:** No change to `hub/main.py` polling — reuses existing 2s `pending_commands` poll -> MQTT `{hub_name}/{dev_type}/command`.
- **Out of scope:** Edge-local cron, PROMINI RTC removal (RTC stays as fallback/degraded display), Telegram push, multi-VPS.

## Decisions

| ID | Topic | Verdict | Rationale |
|----|-------|---------|-----------|
| **D1** | Redis (for Celery/queue) | **DEFER** | Single VPS, APScheduler + Postgres persistence is sufficient for <1k jobs. Redis adds ops burden, persistence gap, and memory pressure. Revisit only if horizontal scaling or sub-second fan-out required. |
| **D2** | shadcn/ui + Tailwind 4 | **ADD** | Vite + Tailwind 4 needs `@tailwindcss/vite`. Adds Radix primitives, `react-day-picker` for Calendar, `cron-parser`+`cronstrue` for cron UX. Cost 40-60 kB gzipped — acceptable for admin dashboard. Replaces ad-hoc Tailwind without breaking `cn()` pattern. |
| **D3** | Convex (realtime backend) | **REJECT** | Overlaps HubGate FastAPI/Postgres authority, introduces second DB/billing, conflicts with existing 3s polling (`POLL_MS`) and same-origin cookie auth. Not needed for cron scheduling. |
| **D4** | SSE / WebSocket push | **DEFER** | Current 3s polling OK per ops (few rooms, low telemetry rate). SSE adds connection pinning on single VPS + Nginx buffering complexity. Keep polling; revisit with `GET /health` load evidence. |
| **D5** | Server scheduler | **ADD** — flexible cron | APScheduler `BackgroundScheduler` + `SQLAlchemyJobStore` + FastAPI `lifespan`. Separate domain table `schedules(id,dev_id,hub_id,cron_expr,payload,tz,enabled)` — not reused `pending_commands` (transient queue). Cron validated, stored, triggered as `pending_commands` rows at fire time. |

## Hub Scaling

- Many Pi hubs, one VPS `100.108.98.30` — scheduler fans out per `hub_id`/`dev_id`. APScheduler single scheduler process; SQLAlchemyJobStore provides persistence across restarts. Job count scales O(schedules), not O(hubs) — 1 job per schedule, not per hub heartbeat.
- `pending_commands` remains hub-poll bottleneck (2s interval, `0.35s` WAL pacing handles burst). Stagger `cron_expr` per hub to avoid thundering herd; add jitter option later if needed.
- No hub code change — hubs remain stateless pollers; VPS is the only scheduler.

## Capabilities

### New
- `server-scheduler`: cron persistence, APScheduler triggering, timezone handling.
- `dashboard-scheduling`: scheduling UI with flexible cron builder and command Select.

### Modified
- `ats-command-relay` (implicit): scheduler now primary initiator; manual dashboard command path unchanged.

## Impact

- **Code:** `server/app/` new `services/scheduler.py`, `routers/schedules.py`, `models/schedule.py`; `dashboard/src/` new `routes/schedules`, shadcn `components/ui/*`, hooks via `api.ts`/`queryKeys.ts`.
- **Database:** New `schedules` table (FK `dev_id`, `hub_id` nullable), indexes on `enabled`+`hub_id`. Reuses `pending_commands` as execution queue — no firmware schema break.
- **Edge/Firmware:** No flash required; bundled payload documented for PROMINI parse.
- **Ops:** VPS systemd restart reloads scheduler via lifespan; no new infra (no Redis/Convex).
- **Risks:** See design.md.

## Risks / Mitigations

- **Cron misfire after VPS downtime:** SQLAlchemyJobStore + `misfire_grace_time` (e.g., 60s) + `coalesce=true` — missed runs coalesce to one, not flood.
- **Timezone drift:** Store `tz=Asia/Jakarta` canonical, convert to UTC for APScheduler; validate on API; preview shows local + UTC.
- **Payload bypasses safety guard:** Bundled `manual+on` is intentional for scheduled warmup only; RBAC admin-only + audit via `schedules` table; manual operator override still respected outside schedule.
- **shadcn bundle bloat:** Tree-shake Radix, lazy-load Calendar/Popover route; 40-60 kB measured, not on critical path.

## Alternatives Considered

- Edge Pi cron (cron on each Pi): rejected — many Pis, clock drift, no central audit, firmware fleet `smsb-iot` hidden AP makes fleet management harder.
- Postgres `pg_cron`: rejected — couples to Postgres extension, less portable for SQLite fallback, no Python payload logic.
