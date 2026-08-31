---
type: concept
governed_by: AGENTS.md
links: [wiki/concept-telemetry-pipeline.md, wiki/workstream-ats-emergency-2026-08.md, wiki/entity-data-model.md]
sources: [server/app/services/alert_engine.py, server/app/services/presence.py, commit:a4a6769]
updated: 2026-08-31
---

# Alert engine

`evaluate_device_thresholds` runs synchronously inside `receive_iot` on every telemetry POST, using `event_time` (WAL-aware) as the alert timestamp.

Temperature: per-device thresholds from `device_threshold_config` (defaults warning 28.0 / critical 32.0 °C, hysteresis 0.5, debounce 60s). A breach above the previous alert's severity within the debounce window is suppressed; recovery below warning-minus-hysteresis resolves all open alerts.

ATS emergency: `EMERGENCY=1` raises `ATS_EMERGENCY` (critical) under the same 60s debounce; `EMERGENCY=0` resolves open ones. Since a4a6769 (deployed 2026-08-31 after the stale-runtime fix) a stuck latch is also auto-resolved server-side: when the payload reports `EMERGENCY=1` but `PLN>210 && GENSET<80` (keys case-insensitive) the engine resolves all open emergency alerts and suppresses new ones — the "genset disconnected while PLN healthy" field condition. That suppression cleared 1233 accumulated spam rows on first contact.

Presence: `resolve_offline_on_telemetry` marks devices online; a 25s `last_seen` cutoff raises `DEVICE_OFFLINE` and derives hub status on `GET /api/hubs`. History charts render detected sample gaps as "hub offline - no samples" bands.
