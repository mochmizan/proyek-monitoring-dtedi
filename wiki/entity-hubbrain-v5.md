---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-telemetry-pipeline.md, wiki/concept-command-path.md, wiki/entity-ats-firmware-chain.md, wiki/entity-hubgate-v5.md]
sources: [hub/main.py, hub/AGENTS.md]
updated: 2026-08-31
---

# HubBrain V5 (hub/)

HubBrain V5 is the single-file edge gateway (`hub/main.py`) running on each Raspberry Pi 4. It bridges local MQTT (`hs109rs/#`) to the HubGate HTTPS API and is the only path telemetry and commands take between the ESP fleet and the server.

Four background threads: whitelist sync (30s `GET /api/devices` with hub headers), command poller (2s `GET /api/hub/commands` → MQTT publish on `{hub_name}/{dev_type}/command` → `/delivered` ack), WAL replay worker (5s cycles, batch 25, 0.35s pacing), and the paho-mqtt loop. All upstream calls use `timeout=5` and TLS-pin the self-signed cert via `TLS_CERT_PATH`.

The offline buffer is a bounded SQLite WAL (`edge_cache.db`): `MAX_PENDING_ROWS=20000` FIFO with 7-day TTL. On replay each row is stamped with `_hub_created_at` (its original enqueue epoch) so the server can restore true capture times — without it, multi-hour outages collapse into a burst at reconnect time.

Each Pi also broadcasts the hidden WPA2 fleet AP `smsb-iot` at `192.168.72.242/24` (hostapd + dnsmasq); all ESP nodes associate to it and share the broker. eth0 carries the campus LAN side (`10.33.102.10` static). The Pi has no RTC battery — chrony corrects the clock from campus NTP `10.33.102.172` on boot.
