---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubbrain-v5.md, wiki/entity-hubgate-v5.md, wiki/entity-ats-firmware-chain.md, wiki/entity-dashboard-spa.md, wiki/concept-time-conventions.md]
sources: [hub/main.py, server/app/routers/iot.py, server/schemasv5.py, commit:d1225f9]
updated: 2026-08-31
---

# Telemetry pipeline

Uplink path: ESP node publishes JSON on `hs109rs/#` (Pi-local broker) → HubBrain `on_message` drops non-whitelisted DEV_IDs (throttled `POST /api/iot/unapproved` for new MACs) → whitelisted payloads `POST /api/iot` with hub headers → Pydantic discriminated union validates → typed row in `temperature_data`/`ats_data` (or legacy `data_table`) with `event_time` → `alert_engine` evaluates synchronously in the same request → dashboard polls history/room-map endpoints every 3s.

When the campus link is down, forwarding fails and the row is enqueued in the hub's bounded WAL (20000 rows FIFO, 7d TTL). On recovery the replay worker drains it paced at 0.35s/row and stamps each payload with `_hub_created_at` — the epoch of original capture. The server prefers that epoch for `event_time`, so an outage of hours replays as data spread across real capture times instead of one giant burst "now". Before d1225f9 (2026-08-31) replay timestamps collapsed to server receive time, which is how a 01:00–03:00 outage looked like a 03:21 alert storm.

The dashboard side is cache-first: TanStack Query `keepPreviousData` + `STALE_MS 10s` means the 3s poll updates in place without blank flashes (fixed 2026-08-31; see [entity-dashboard-spa.md](entity-dashboard-spa.md)).
