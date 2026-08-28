# Spec: server-scheduler

## Purpose

VPS-authoritative flexible cron scheduler that persists cron expressions and fires `pending_commands` via APScheduler, replacing PROMINI RTC for ATS warmup.

## ADDED Requirements

### Requirement: Persist schedules with cron and payload
The system SHALL persist schedules in a dedicated `schedules(id,dev_id,hub_id,cron_expr,payload,tz,enabled)` table, validated and timezone-aware.

#### Scenario: Create schedule with flexible cron
- **WHEN** an admin `POST /api/schedules` with `{"dev_id":"ATS-xxxx","cron_expr":"0 18 * * 0","payload":{"mode":"manual","start_genset":"on"},"tz":"Asia/Jakarta","enabled":true}`
- **THEN** the system validates `cron_expr` via `cron-parser` (5-field), validates `payload` against whitelist, stores the row with `tz=Asia/Jakarta`, and returns 201 with `next_run` and `human` (cronstrue)

#### Scenario: Reject invalid cron
- **WHEN** a client posts `cron_expr="* * *"` or `"@reboot"`
- **THEN** the system responds 422 with a validation error and creates no row or job

#### Scenario: Timezone handling
- **WHEN** a schedule is stored with `tz=Asia/Jakarta`
- **THEN** the APScheduler `CronTrigger` is registered with that timezone and `GET /api/schedules` returns `next_run` in both local and UTC, with Jakarta as default when `tz` omitted

### Requirement: APScheduler triggers pending_commands
The system SHALL use APScheduler 3.x `BackgroundScheduler` with `SQLAlchemyJobStore` and FastAPI `lifespan` to fire each enabled schedule as an insert into `pending_commands` for hub polling.

#### Scenario: Cron fires inserts pending command
- **WHEN** the cron for schedule `id=1` fires
- **THEN** the system executes `fire_schedule(1)` which inserts a row into `pending_commands (hub_id, dev_id, payload)` where `payload={"mode":"manual","start_genset":"on"}` bundled to bypass `check_genset_mode`, and the hub delivers it via 2s poll -> MQTT `{hub_name}/{dev_type}/command`

#### Scenario: Scheduler survives restart
- **WHEN** the VPS restarts and FastAPI `lifespan` starts
- **THEN** the scheduler rehydrates all `enabled=true` schedules from the DB into jobs (`id=schedule-{id}`) with `coalesce=true`, `misfire_grace_time=60`, `max_instances=1` via `SQLAlchemyJobStore`

#### Scenario: Misfire coalesce
- **WHEN** the VPS was down during a scheduled fire
- **THEN** at most one coalesced fire is executed after recovery (not a flood), per `coalesce=true` and `misfire_grace_time`

### Requirement: CRUD lifecycle syncs scheduler jobs
The system SHALL keep APScheduler jobs in sync with `schedules` CRUD: create adds job, patch reschedules, delete removes job, toggle enabled adds/removes job.

#### Scenario: Disable schedule removes job
- **WHEN** an admin `PATCH /api/schedules/1` with `{"enabled": false}`
- **THEN** the system updates the row, calls `scheduler.remove_job("schedule-1")`, and subsequent crons do not fire

#### Scenario: Update cron reschedules
- **WHEN** an admin `PATCH /api/schedules/1` with `{"cron_expr":"0 7 * * 1,4"}`
- **THEN** the system validates the new cron, updates the row, and calls `scheduler.reschedule_job` with new `CronTrigger` params

### Requirement: RBAC and validation
The system SHALL enforce RBAC on `/api/schedules` (admin write, operator read) and validate payload whitelist.

#### Scenario: Operator cannot create schedule
- **WHEN** a user with `operator` role `POST /api/schedules`
- **THEN** the system responds 403 Forbidden

#### Scenario: Payload whitelist enforced
- **WHEN** a client posts `payload={"mode":"invalid"}`
- **THEN** the system responds 422 and creates no schedule

### Requirement: Firmware bundling contract
The system SHALL support bundled payload `{"mode":"manual","start_genset":"on"}` as the canonical scheduled warmup, delivered atomically so firmware executes `<M,manual>` then `<SGM,on>` without `check_genset_mode` block.

#### Scenario: Bundled warmup bypasses guard
- **WHEN** the scheduler fires the bundled payload for an ATS device in `manual`
- **THEN** `fixed_wemos_mqtt_raspi.ino` forwards both sub-commands via bounded serial and PROMINI `fsm_w_serial.ino` executes them, starting genset despite prior manual mode

