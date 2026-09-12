---
type: concept
governed_by: AGENTS.md
links: []
sources: [AGENTS.md]
updated: 2026-09-12
---

# smsb wiki index

Compiled project knowledge for the smsb IoT smart-building monitoring stack. Governed by [AGENTS.md](../AGENTS.md). How-to-work rules live there; this wiki says what is true.

## Entities

- [entity-hubgate-v5.md](entity-hubgate-v5.md) — FastAPI cloud gateway (server/): canonical `app.main:api` entrypoint, auth/RBAC, active PostgreSQL 16 `smsb_prod` persistence (4.15M rows migrated), batch ingestion, presence sweeper
- [entity-hubbrain-v5.md](entity-hubbrain-v5.md) — Raspberry Pi edge gateway (hub/): MQTT bridge, WAL cache, command dispatch
- [entity-dashboard-spa.md](entity-dashboard-spa.md) — React 19 SPA (dashboard/): routes, edge-to-edge zero-roundness canvas, floating AppSidebar, 4-tier jittered polling, visual CronBuilder, WIB rendering, custom SVG charts
- [entity-ats-firmware-chain.md](entity-ats-firmware-chain.md) — Two-MCU ATS controller: PROMINI FSM + WEMOS_ATS bridge, serial framing, field remediation for node 68:C6:3A:D7:60:47
- [entity-firmware-fleet.md](entity-firmware-fleet.md) — Fleet node specifications: WEMOS_TS, WEMOS_AC, WEMOS_ATS, PROMINI pinouts, I2C addresses, EEPROM layouts
- [entity-security-auth.md](entity-security-auth.md) — Authentication & authorization model: RBAC matrix, Argon2id, session cookies, SlowAPI rate limiting, security remediations (SEC-01, SEC-03, SEC-06, SEC-10)
- [entity-deploy-pipeline.md](entity-deploy-pipeline.md) — Push-deploy to VPS via post-receive hook; normalized server runtime path, V8 heap cap, Alembic migration pre-flight gate, credential rotation
- [entity-devops-infrastructure.md](entity-devops-infrastructure.md) — VPS topology (8GB host / 4 vCPUs, 4GB SMSB profile, CTFd co-tenancy), Nginx reverse proxy, TLS termination, systemd isolation (--workers 1 --limit-concurrency 50, MemoryMax=1.8G), active PostgreSQL 16 `smsb_prod`, push-deploy pre-flight gating
- [entity-data-model.md](entity-data-model.md) — HubGate V5 tables, composite primary keys (data_id, timestamp), active PostgreSQL 16 `smsb_prod` schema (4.15M rows, 100% parity), declarative range partitioning, BRIN indexes, composite indexes, unique constraints, and schema nullability

## Concepts

- [concept-telemetry-pipeline.md](concept-telemetry-pipeline.md) — End-to-end data flow: ESP → MQTT → hub WAL → HTTPS → single-transaction DB ingest with boundary timestamp filtering → dashboard
- [concept-downsampling-v2.md](concept-downsampling-v2.md) — Single-pass SQL epoch bucketing, min/max envelopes, and sub-second 30d SLAs on active PostgreSQL 16
- [concept-presence-engine.md](concept-presence-engine.md) — Decoupled 15s background presence sweeper, detection lag SLA (<= 75s), and read-only query invariant (4GB profile with CTFd co-tenancy)
- [concept-frontend-navigation.md](concept-frontend-navigation.md) — TanStack Router intent preloading, background idle route warmup, floating sidebar & drawer navigation, and 401 unauth handling
- [concept-frontend-resilience.md](concept-frontend-resilience.md) — Active ErrorBoundary mounting hierarchy, query retry policies, 401 redirect interceptors, offline/reconnecting UX, scroll restoration
- [concept-state-management.md](concept-state-management.md) — TanStack Query server cache, constants.ts, persistent sidebarStore, background tab polling suspension contract, Rollup manualChunks, lazy dialogs
- [concept-database-lifecycle.md](concept-database-lifecycle.md) — Hardened connection pool sizing (20/10), transaction atomicity, active PostgreSQL 16 `smsb_prod` (4.15M rows migrated at 100% parity) with declarative monthly range partitioning & BRIN, O(1) retention pruning, 4GB profile with CTFd co-tenancy, SQLite 3 edge WAL
- [concept-edge-resilience.md](concept-edge-resilience.md) — MQTT bridge durability, offline WAL FIFO queueing, rate pacing, timestamp preservation, failure modes
- [concept-command-path.md](concept-command-path.md) — Downlink: web command → pending_commands → hub poll → MQTT → serial frame
- [concept-alert-engine.md](concept-alert-engine.md) — Threshold evaluation, debounce, hysteresis, ATS emergency auto-resolve
- [concept-observability-monitoring.md](concept-observability-monitoring.md) — Structured JSON logging with X-Request-ID tracing, JSON formatter for app/error logs, health probe contracts, alert dispatching
- [concept-production-readiness.md](concept-production-readiness.md) — Holistic production gap assessment across server, dashboard, edge, firmware, and ops (PostgreSQL 16 live cutover & migration pre-flight gating resolved)
- [concept-time-conventions.md](concept-time-conventions.md) — UTC storage, _hub_created_at replay epochs, Z-suffix contract, WIB rendering

## Workstreams

- [workstream-production-grade-roadmap.md](workstream-production-grade-roadmap.md) — Actionable production-grade refactoring plan: P0 Blockers (P0-2 PostgreSQL 16 live cutover completed with 4.15M rows at 100% parity), P1 Hardening, P2 Optimization
- [workstream-backend-hardening-v5.md](workstream-backend-hardening-v5.md) — 6-phase backend hardening: engine pool limits, downsampling v2, batch ingestion, presence worker, zero-lock verification, declarative partitioning & completed 4.15M row live cutover
- [workstream-ats-emergency-2026-08.md](workstream-ats-emergency-2026-08.md) — Genset-disconnect EMERGENCY latch: timeline, decisions, pending reflash and field node ATS remediation runbook
- [workstream-firmware-proofing.md](workstream-firmware-proofing.md) — 14-gap hardening of PROMINI/WEMOS_ATS (dcfeb84), bench soak pending
- [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md) — Replacing firmware Sunday warmup with server APScheduler cron
- [workstream-shadcn-revert.md](workstream-shadcn-revert.md) — Full shadcn redesign attempt and revert; retained perf polish

## Notes

All historical notes and benchmark baselines have been codified into the wiki, automated tests (pytest/vitest), and operational runbooks (`docs/runbooks/postgres_cutover_runbook.md`, `docs/runbooks/field_node_ats_remediation.md`). Working notes are archived in git history.


