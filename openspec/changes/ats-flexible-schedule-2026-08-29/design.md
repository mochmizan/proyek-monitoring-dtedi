# Design: ATS Flexible Scheduling + Shard Stack

## Context

Single VPS `100.108.98.30` serves many Pi hubs. Current PROMINI weekly warmup (RTC DS3231, Sunday 18:00) drifts, is unconfigurable, and is blocked by `check_genset_mode`. Dashboard polls 3s (`POLL_MS`) — proven sufficient. Researchers enriched: shadcn Vite+Tailwind4 needs `@tailwindcss/vite`, `react-day-picker`, `cron-parser`+`cronstrue`, Radix primitives (40-60 kB). APScheduler 3.x with `SQLAlchemyJobStore` + lifespan + separate `schedules` table is the right scheduler primitive. Firmware requires bundled `{mode:manual, start_genset:on}` to bypass guard.

## Goals / Non-Goals

**Goals:** VPS-authoritative flexible cron via dashboard; cron validation + human preview; RBAC; timezone-correct fire; reuse `pending_commands` poll; shadcn UI foundation.

**Non-Goals:** Edge scheduler, RTC removal, Redis/Convex/SSE, sub-second realtime, AC/TS scheduling (extensible but not primary).

## Architecture

```
ESP ATS (WEMOS) --MQTT hs109rs/#--> Pi hub (Mosquitto) --HTTPS WAL 0.35s--> VPS HubGate
                                                          <-poll 2s pending_commands--
VPS: APScheduler (cron) --insert--> pending_commands --poll--> hub --MQTT {hub_name}/{dev_type}/command--> ESP --> PROMINI serial <SGM,on>
Dashboard --CRUD /api/schedules (cron_expr, payload, tz)--> VPS schedules table --APScheduler job--> pending_commands
```

- **Trigger path:** APScheduler job fires per `cron_expr` (tz `Asia/Jakarta`) -> service inserts row into `pending_commands` (`hub_id`, `dev_id`, `payload`, `created_at`). Hub 2s poll picks it up, publishes MQTT, deletes on ACK (existing flow).
- **No new hub protocol.** Hub `MAX_PENDING_ROWS=20000` WAL absorbs burst if many schedules fire at once.

## Decisions

- **D2 shadcn ADD detail:** Use `shadcn` CLI with `style: default`, `baseColor: zinc` matching dark `--color-background:#09090b`, `cssVariables: true`. Tailwind 4 via `@tailwindcss/vite` plugin (no PostCSS). Components: `Dialog` (create/edit), `Select` (command pick + cron presets), `Calendar` (date for one-off preview bound via `Popover`), `Popover`, `Table` (schedule list), `Switch` (enabled), `Button`, `Input`, `Label`, `Badge`. Plus `react-day-picker` peer dep.
- **D5 scheduler ADD detail:** `BackgroundScheduler` with `SQLAlchemyJobStore(url=settings.DATABASE_URL)`, `job_defaults={coalesce: True, max_instances: 1, misfire_grace_time: 60}`. Mounted in FastAPI `lifespan` (not startup event).

## APScheduler Lifespan Snippet

```python
# server/app/services/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from contextlib import asynccontextmanager
from fastapi import FastAPI

scheduler: BackgroundScheduler | None = None

def fire_schedule(schedule_id: int):
    # inside app context: load schedule row, insert into pending_commands
    from app.db import SessionLocal
    from app.models.schedule import Schedule
    from app.models.pending_command import PendingCommand
    db = SessionLocal()
    try:
        s = db.get(Schedule, schedule_id)
        if not s or not s.enabled:
            return
        db.add(PendingCommand(hub_id=s.hub_id, dev_id=s.dev_id, payload=s.payload))
        db.commit()
    finally:
        db.close()

@asynccontextmanager
async def scheduler_lifespan(app: FastAPI):
    global scheduler
    jobstores = {"default": SQLAlchemyJobStore(url=settings.DATABASE_URL)}
    scheduler = BackgroundScheduler(jobstores=jobstores, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60})
    # rehydrate jobs from schedules table
    for s in load_enabled_schedules():
        scheduler.add_job(fire_schedule, "cron", args=[s.id], id=f"schedule-{s.id}", **cron_kwargs(s.cron_expr, s.tz))
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

# server/app/main.py
# app = FastAPI(lifespan=scheduler_lifespan)
```

- On `POST/PATCH /api/schedules`, add/update `scheduler.add_job` / `scheduler.reschedule_job`. On `DELETE`, `remove_job`. `cron_kwargs` parses `cron_expr` via `croniter`/`cron-parser` validation first.

## DB Schema

```sql
-- server/app/models/schedule.py  (Alembic migration)
CREATE TABLE schedules (
  id SERIAL PRIMARY KEY,
  dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
  hub_id VARCHAR REFERENCES hub_table(hub_id) ON DELETE CASCADE,
  cron_expr VARCHAR(64) NOT NULL,          -- e.g. "0 18 * * 0" (Sun 18:00) flexible
  payload JSONB NOT NULL,                  -- {"mode":"manual","start_genset":"on"} or {"cmd":"<RST,rst>"}
  tz VARCHAR(32) NOT NULL DEFAULT 'Asia/Jakarta',
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_by VARCHAR NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_schedules_enabled_hub ON schedules(enabled, hub_id);
CREATE INDEX ix_schedules_dev ON schedules(dev_id);
-- pending_commands is reused as-is (id, hub_id, dev_id, payload, created_at, claimed_at)
```

- Validation: `cron_expr` 5-field standard cron; reject `@reboot` etc. `payload` Zod/Pydantic whitelist: `mode` in `auto/manual`, `start_genset` in `on/off`, `cmd` patterns `<SGM,...>` etc.
- Timezone: Store canonical `Asia/Jakarta` (WIB, UTC+7, no DST). APScheduler `CronTrigger` with `timezone=pytz.timezone(s.tz)`. API returns next 3 fire times using `cron-parser`.

## Dashboard — shadcn Components

- Route `dashboard/src/routes/schedules.tsx` (TanStack Router file route).
- Hooks: `useSchedules()` (GET), `useCreateSchedule()`, `useUpdateSchedule()`, `useDeleteSchedule()` in `lib/api.ts` via `queryKeys.schedules`.
- UI:
  - `Table` lists schedules: device, hub, cron, human preview (`cronstrue.toString(cron_expr)`), payload badge, enabled `Switch`, actions.
  - `Dialog` + `Select` for command: presets `Warmup (manual+on)`, `Cooldown (auto)`, `Reset`, `Custom JSON`. Select binds to `payload`.
  - `Popover` + `Calendar` (react-day-picker) for next-run preview / one-off date helper (optional, not stored — just preview).
  - `Input` for cron with live `cronstrue` preview + `cron-parser` validation error.
  - `Select` for hub/dev pick (filtered to ATS `dev_type` initially, extensible).
- Polling: schedule list `STALE_MS` normal; not live-polled at 3s — only on mutation invalidate.

## Timezone

- Canonical `Asia/Jakarta` (WIB UTC+7). Dashboard sends `tz` (default Jakarta), preview renders local + UTC. APScheduler trigger timezone-aware; stored UTC internally but displayed Jakarta.

## Firmware Bundling

- To bypass `PROMINI.ino: check_genset_mode()` guard, scheduled warmup sends bundled JSON: `{"mode":"manual","start_genset":"on"}` as single `pending_commands.payload`. Hub publishes atomically to `{hub_name}/ATS/command` → `fixed_wemos_mqtt_raspi.ino` (512B buf, bounded serial) → serial `<M,manual>` then `<SGM,on>` in sequence. Duration is separate `off` schedule or timeout param (`durationSec` optional field in payload, firmware respects if present).
- Single-command payloads (e.g., `{"cmd":"<RST,rst>"}`) also supported for reset.
- No PROMINI reflash — parser already handles `<M,*>` and `<SGM,*>`.

## Risks

- Single VPS scheduler is SPOF — mitigation: SQLAlchemyJobStore persistence + systemd auto-restart, health check `GET /health` includes scheduler status.
- Thundering herd: many schedules at same minute -> burst `pending_commands` inserts -> WAL 0.35s pacing throttles; advise stagger in docs.
- Cron injection: validate via `cron-parser` before store; reject shell-style extensions.

## Migration

1. Alembic add `schedules` table.
2. Deploy scheduler service (no hub change).
3. Dashboard shadcn init (`@tailwindcss/vite` + shadcn CLI) on feature branch, add schedules route.
4. PROMINI RTC left as fallback; no firmware deploy required.
5. Seed one schedule `0 18 * * 0` manual+on to parity-match old behavior; verify WAL poll delivers.

