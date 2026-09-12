---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-dashboard-spa.md, wiki/concept-command-path.md, wiki/workstream-ats-emergency-2026-08.md]
sources: [server/modelsv5.py, server/app/services/scheduler.py, server/app/routers/schedules.py, dashboard/src/routes/schedules.tsx, commit:b4dcec6, git:openspec/changes/ats-flexible-schedule-2026-08-29/ (archived)]
updated: 2026-08-31
---

# Flexible scheduling workstream

**Status: live since 2026-08-29 (b4dcec6); firmware fallback disabled 2026-08-31.**

The ATS weekly warmup used to be an autonomous PROMINI behavior (`WARMUP_DAY 0`, 18:00) — a battery-less RTC drifted it uselessly (06:00→11:11 over weeks), which is the root cause of the Aug-30 emergency. This workstream moved scheduling server-side: a `schedules` table (5-field cron, `tz` Asia/Jakarta, JSON payload, enabled, next_run_at, alembic b7c9e2f1a4d8), an APScheduler BackgroundScheduler in the app lifespan (coalesce, misfire_grace 60, CANONICAL_TZ), CRUD/preview/run-now admin endpoints, and a `/schedules` dashboard route with cron helpers (`src/lib/cron.ts`).

Firing a job enqueues the payload into `pending_commands` like any manual command; warmup uses the bundled `{"mode":"manual","start_genset":"on"}` which deliberately bypasses the "last known mode must be manual" guard. Hub delivery follows the standard command path (2s poll). The canonical PROMINI's autonomous warmup is disabled (`6a9823a` docs, dcfeb84 code), making the server the single scheduling authority — no more silent Sunday starts.
