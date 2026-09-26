---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-ats-firmware-chain.md, wiki/entity-hubbrain-v5.md, wiki/entity-hubgate-v5.md, wiki/entity-dashboard-spa.md, wiki/workstream-flexible-scheduling.md]
sources: [server/app/routers/commands.py, server/schemasv5.py, dashboard/src/hooks/useCommandLifecycle.ts, hub/main.py, firmware/WEMOS_ATS/WEMOS_ATS.ino]
updated: 2026-09-26
---

# Command path (downlink)

Dashboard Controls → `POST /api/devices/{dev_id}/command` (admin/operator; `reset` admin-only). `ATSCommand` / `ACCommand` validate payload structure; for ATS, a bare `start_genset:"on"` is rejected unless the device's last known state was manual — schedules bundle `{"mode":"manual","start_genset":"on"}` to bypass deliberately. The row lands in `pending_commands` with an initial `status` ("pending").

Client lifecycle management runs via `useCommandLifecycle`: upon queueing, the UI receives `command_id` and polls `GET /api/commands/{command_id}` every 1.5s (up to 12s timeout) while locking the form controls against double dispatch. When HubBrain reports a successful local MQTT publish, the API returns `status: "dispatched"` with tz-aware `delivered_at`; the UI explicitly states that device execution remains unconfirmed.

HubBrain polls `GET /api/hub/commands` every 2s, derives the MQTT topic `{hub_name}/{dev_type}/command`, publishes, and acknowledges broker acceptance via `POST /api/hub/commands/{command_id}/dispatched`, which records `delivered_at = datetime.now(UTC)` as the dispatch timestamp. The deprecated `/delivered` alias has identical dispatch-only semantics for rolling upgrades. WEMOS_ATS may subsequently receive the MQTT message and write a serial frame to the Pro Mini, but the current protocol has no device-to-server execution ACK.

`RST` is safe for the building: boot state holds relays HIGH (PLN contactor closed), so a reset during healthy PLN never drops load. What `RST` cannot do is clear an EMERGENCY on old firmware — if the FSM's warmup is overdue and the genset is disconnected it re-latches after the boot retry cycle (proven live 2026-08-31, see [workstream-ats-emergency-2026-08.md](workstream-ats-emergency-2026-08.md)).
