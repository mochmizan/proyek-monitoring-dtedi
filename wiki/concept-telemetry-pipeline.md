---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubbrain-v5.md, wiki/entity-hubgate-v5.md, wiki/entity-ats-firmware-chain.md, wiki/entity-dashboard-spa.md, wiki/concept-time-conventions.md]
sources: [hub/main.py, server/app/routers/iot.py, server/schemasv5.py, dashboard/src/hooks/useDeviceHistory.ts, dashboard/src/components/device/HistoryChart.tsx, commit:d1225f9]
updated: 2026-09-01
---

# Telemetry pipeline

Uplink path: ESP node publishes JSON on `hs109rs/#` (Pi-local broker) → HubBrain `on_message` drops non-whitelisted DEV_IDs (throttled `POST /api/iot/unapproved` for new MACs) → whitelisted payloads are dispatched either singly to `POST /api/iot` or in batches up to 100 items via `POST /api/iot/batch` with hub credentials → Pydantic discriminated union validates payload structures → typed rows in `temperature_data`/`ats_data` (or legacy `data_table`) with deterministic `data_id = sha256(dev_id:timestamp_iso)[:16]`.

Bulk ingestion uses `bulk_insert_or_ignore` with dialect-specific idempotency (`ON CONFLICT (dev_id, timestamp) DO NOTHING` on PostgreSQL 16 and `INSERT OR IGNORE` on SQLite). In batch ingestion, alert threshold rules and device presence recovery (`resolve_offline_on_telemetry`) are evaluated only on the newest reading per device in the batch, eliminating redundant database contention.

When the campus link is down, forwarding fails and the row is enqueued in the hub's bounded WAL (20000 rows FIFO, 7d TTL). On recovery the replay worker drains it paced at 0.35s/row and stamps each payload with `_hub_created_at` — the epoch of original capture. The server prefers that epoch for `event_time`, so an outage of hours replays as data spread across real capture times instead of one giant burst "now". Before d1225f9 (2026-08-31) replay timestamps collapsed to server receive time, which is how a 01:00–03:00 outage looked like a 03:21 alert storm.

The dashboard side is cache-first: TanStack Query `keepPreviousData` + `STALE_MS 10s` ensures smooth background updates. History visualization via `useDeviceHistory` queries [concept-downsampling-v2.md](concept-downsampling-v2.md) which returns single-pass aggregated buckets with min/max envelopes bounded to 1000 points. On ATS devices, `HistoryChart` separates telemetry into a 3-panel stacked layout (PLN Grid AC, Genset AC, and Starter Battery DC with 11.8V warning / 11.2V critical thresholds) featuring independent auto-scaled 12% padding Y-axes and sharing synchronized time axes and crosshair inspection (see [entity-dashboard-spa.md](entity-dashboard-spa.md)).
