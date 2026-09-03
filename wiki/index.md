---
type: concept
governed_by: AGENTS.md
links: []
sources: [AGENTS.md]
updated: 2026-09-03
---

# smsb wiki index

Compiled project knowledge for the smsb IoT smart-building monitoring stack. Governed by [AGENTS.md](../AGENTS.md). How-to-work rules live there; this wiki says what is true.

## Entities

- [entity-hubgate-v5.md](entity-hubgate-v5.md) — FastAPI cloud gateway (server/): canonical `app.main:api` entrypoint, auth/RBAC, DB engine hardening, batch ingestion, presence sweeper
- [entity-hubbrain-v5.md](entity-hubbrain-v5.md) — Raspberry Pi edge gateway (hub/): MQTT bridge, WAL cache, command dispatch
- [entity-dashboard-spa.md](entity-dashboard-spa.md) — React 19 SPA (dashboard/): routes, TanStack Query polling, WIB rendering, custom SVG charts
- [entity-ats-firmware-chain.md](entity-ats-firmware-chain.md) — Two-MCU ATS controller: PROMINI FSM + WEMOS_ATS bridge, serial framing
- [entity-firmware-fleet.md](entity-firmware-fleet.md) — Fleet node specifications: WEMOS_TS, WEMOS_AC, WEMOS_ATS, PROMINI pinouts, I2C addresses, EEPROM layouts
- [entity-security-auth.md](entity-security-auth.md) — Authentication & authorization model: RBAC matrix, Argon2id, session cookies, SlowAPI rate limiting, security remediations (SEC-01, SEC-03, SEC-06, SEC-10)
- [entity-deploy-pipeline.md](entity-deploy-pipeline.md) — Push-deploy to VPS via post-receive hook; normalized server runtime path
- [entity-devops-infrastructure.md](entity-devops-infrastructure.md) — VPS topology, Nginx reverse proxy, TLS termination, systemd isolation (`app.main:api`), backup & recovery
- [entity-data-model.md](entity-data-model.md) — HubGate V5 tables, composite indexes, unique constraints, and schema nullability

## Concepts

- [concept-telemetry-pipeline.md](concept-telemetry-pipeline.md) — End-to-end data flow: ESP → MQTT → hub WAL → HTTPS → single-transaction DB ingest → dashboard
- [concept-downsampling-v2.md](concept-downsampling-v2.md) — Single-pass SQL epoch bucketing, min/max envelopes, and sub-second 30d SLAs
- [concept-presence-engine.md](concept-presence-engine.md) — Decoupled 5s background presence sweeper, detection lag SLA (<= 30s), and read-only query invariant
- [concept-frontend-navigation.md](concept-frontend-navigation.md) — TanStack Router intent preloading, background idle route warmup, progress bar, and 401 unauth handling
- [concept-frontend-resilience.md](concept-frontend-resilience.md) — Active ErrorBoundary mounting hierarchy, query retry policies, 401 redirect interceptors, offline/reconnecting UX, scroll restoration
- [concept-state-management.md](concept-state-management.md) — TanStack Query server cache, constants.ts, background tab polling suspension contract, query key stability
- [concept-database-lifecycle.md](concept-database-lifecycle.md) — Connection pool sizing, transaction atomicity, SQLite WAL vs PostgreSQL 16 MVCC, session window throttling, Alembic discipline
- [concept-edge-resilience.md](concept-edge-resilience.md) — MQTT bridge durability, offline WAL FIFO queueing, rate pacing, timestamp preservation, failure modes
- [concept-command-path.md](concept-command-path.md) — Downlink: web command → pending_commands → hub poll → MQTT → serial frame
- [concept-alert-engine.md](concept-alert-engine.md) — Threshold evaluation, debounce, hysteresis, ATS emergency auto-resolve
- [concept-observability-monitoring.md](concept-observability-monitoring.md) — Structured JSON logging with X-Request-ID tracing, Prometheus/APM metrics void, health probe contracts, alert dispatching
- [concept-production-readiness.md](concept-production-readiness.md) — Holistic production gap assessment across server, dashboard, edge, firmware, and ops
- [concept-time-conventions.md](concept-time-conventions.md) — UTC storage, _hub_created_at replay epochs, Z-suffix contract, WIB rendering

## Workstreams

- [workstream-production-grade-roadmap.md](workstream-production-grade-roadmap.md) — Actionable production-grade refactoring plan: P0 Blockers, P1 Hardening, P2 Optimization
- [workstream-backend-hardening-v5.md](workstream-backend-hardening-v5.md) — 6-phase backend hardening: engine pool limits, downsampling v2, batch ingestion, presence worker, zero-lock verification
- [workstream-ats-emergency-2026-08.md](workstream-ats-emergency-2026-08.md) — Genset-disconnect EMERGENCY latch: timeline, decisions, pending reflash
- [workstream-firmware-proofing.md](workstream-firmware-proofing.md) — 14-gap hardening of PROMINI/WEMOS_ATS (dcfeb84), bench soak pending
- [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md) — Replacing firmware Sunday warmup with server APScheduler cron
- [workstream-shadcn-revert.md](workstream-shadcn-revert.md) — Full shadcn redesign attempt and revert; retained perf polish


