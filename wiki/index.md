---
type: concept
governed_by: AGENTS.md
links: []
sources: [AGENTS.md]
updated: 2026-08-31
---

# smsb wiki index

Compiled project knowledge for the smsb IoT smart-building monitoring stack. Governed by [AGENTS.md](../AGENTS.md). How-to-work rules live there; this wiki says what is true.

## Entities

- [entity-hubgate-v5.md](entity-hubgate-v5.md) — FastAPI cloud gateway (server/): routers, auth/RBAC, DB, ingestion
- [entity-hubbrain-v5.md](entity-hubbrain-v5.md) — Raspberry Pi edge gateway (hub/): MQTT bridge, WAL cache, command dispatch
- [entity-dashboard-spa.md](entity-dashboard-spa.md) — React 19 SPA (dashboard/): routes, TanStack Query polling, WIB rendering
- [entity-ats-firmware-chain.md](entity-ats-firmware-chain.md) — Two-MCU ATS controller: PROMINI FSM + WEMOS_ATS bridge, serial framing
- [entity-deploy-pipeline.md](entity-deploy-pipeline.md) — Push-deploy to VPS via post-receive hook; legacy runtime path compat
- [entity-data-model.md](entity-data-model.md) — HubGate V5 tables and relationships (SQLite prod ~430MB)

## Concepts

- [concept-telemetry-pipeline.md](concept-telemetry-pipeline.md) — End-to-end data flow: ESP → MQTT → hub WAL → HTTPS → DB → dashboard
- [concept-command-path.md](concept-command-path.md) — Downlink: web command → pending_commands → hub poll → MQTT → serial frame
- [concept-alert-engine.md](concept-alert-engine.md) — Threshold evaluation, debounce, hysteresis, ATS emergency auto-resolve
- [concept-time-conventions.md](concept-time-conventions.md) — UTC storage, _hub_created_at replay epochs, Z-suffix contract, WIB rendering

## Workstreams

- [workstream-ats-emergency-2026-08.md](workstream-ats-emergency-2026-08.md) — Genset-disconnect EMERGENCY latch: timeline, decisions, pending reflash
- [workstream-firmware-proofing.md](workstream-firmware-proofing.md) — 14-gap hardening of PROMINI/WEMOS_ATS (dcfeb84), bench soak pending
- [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md) — Replacing firmware Sunday warmup with server APScheduler cron
- [workstream-shadcn-revert.md](workstream-shadcn-revert.md) — Full shadcn redesign attempt and revert; retained perf polish
