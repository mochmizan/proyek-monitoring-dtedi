---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-ats-firmware-chain.md, wiki/concept-alert-engine.md, wiki/concept-command-path.md, wiki/entity-deploy-pipeline.md, wiki/workstream-firmware-proofing.md, wiki/workstream-flexible-scheduling.md]
sources: [server/app/services/alert_engine.py, docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md, commit:a4a6769, commit:acd4f00, notes/field-ops.md]
updated: 2026-08-31
---

# ATS emergency workstream (Aug 2026)

**Status: software-contained; permanent fix (reflash) pending field access.**

Timeline: the Sunday warmup on pre-dcfeb84 PROMINI had drifted (no NTP, no RTC) from 18:00 to ~11:11 WIB. With the genset physically disconnected (reads ~55V floating, PLN healthy 217–225V), the boot start-retry cycle exhausted MAX attempts and latched `EMERGENCY_GENSET` on 2026-08-30 04:11 UTC — by design a stuck latch cleared only by `RST`. The engine then logged a critical alert every debounce window (~60s) for 14h+, and a hub outage folded the replay burst into a fake 03:21 "alert storm" (fixed by `_hub_created_at`, see [concept-telemetry-pipeline.md](concept-telemetry-pipeline.md)).

Decisions, in order:
- `RST` issued live 2026-08-31 11:24 WIB to test the theory: device rebooted, retried the genset MAX times, re-latched — proving old firmware cannot be cleared by reset while warmup is overdue and the genset is disconnected. No campus impact (relays held HIGH, PLN continuous).
- Server-side auto-resolve (a4a6769): `EMERGENCY=1` with `PLN>210 && GENSET<80` resolves and suppresses — containment for any unit still on old firmware. Initially appeared dead; the real cause was the stale legacy runtime dir (see [entity-deploy-pipeline.md](entity-deploy-pipeline.md)). Once the deploy path was fixed it cleared all 1233 open alerts on first telemetry and the spam stopped.
- Root fix is flashing proofed `PROMINI` + `WEMOS_ATS` (WARMUP disabled, PLN-priority FSM) — pending physical access to the bench/field units. Until then the latch will re-appear on each warmup window and the server auto-resolve keeps it cosmetic-only.
