# IoT temperature monitoring system — design spec

**Date:** 2026-07-01
**Status:** design approved by user, pending self-review corrections below

## 1. Project overview

Professor-assigned capstone project: a scalable IoT monitoring system, temperature-only in scope, first deployed as a testbed in the campus building's server room. A VPS on the building's server network has been allocated for the project by the professor.

**Immediate scope (this build):** up to 4 rooms — the server room, Ecolab (per Pak Isnan's request), and 2 rooms to be identified.

**Long-term vision (explicitly out of scope for this build):** building-wide deployment across 8 selasar, one hub per selasar, with a dashboard that can select and monitor any hub. The architecture below is designed so this scale-up is additive (new rooms = new topic branches / new paired devices), not a redesign — but building it out is not part of the current deliverable.

## 2. Goals

- Production-grade and scalable from day one, not a one-off prototype
- Web dashboard with AAA: Authentication, Authorization, and Accounting
- Dashboard can select which room/device to monitor
- Historical data logging and graphing
- "Hermes" — a chat-capable Telegram agent for querying room/device condition and issuing limited commands

## 3. Modules

Three independently deployable firmware/module types, matching the professor's brief:

- **Temperature module** — the core monitored parameter, deployed in every room.
- **ATS module** — power source status (e.g. PLN vs genset/UPS).
- **AC module** — air conditioner monitoring and IR control.

All three publish to the same central MQTT broker under a shared topic convention (Section 6), so the dashboard and backend treat them uniformly regardless of room or module type.

## 4. Hardware

| Component | Recommendation | Notes |
|---|---|---|
| MCU | ESP32-WROOM-32U (external antenna pad) + 2.4GHz dipole | Use the "U" variant especially for the ATS module if mounted near/inside metal switchgear — steel enclosures attenuate RF badly |
| Temperature/humidity | SHT31-D (I2C, ±0.3°C temp / ±2% RH) | Industrial-grade accuracy; humidity reading is a useful free bonus for condensation/corrosion risk |
| Multi-point temperature | DS18B20 waterproof probes (1-Wire) | Multiple probes share one GPIO via unique serial numbers — cheap spatial coverage (e.g. rack intake + exhaust + ambient) |
| ATS sensing | **Recommended default:** PZEM-004T v3 (UART/Modbus, ±0.5% accuracy on V/I/P/frequency/power factor/energy) | Cheaper alternative: optocoupler-based presence-only sensing (PC817 + resistor divider) if power-quality data isn't required — **not yet confirmed with the user, see Open questions** |
| AC — IR transmit | 940nm IR LED + 2N2222/2N3904 transistor driver | A few thousand rupiah in parts, not a pre-made module |
| AC — control library | IRremoteESP8266 | Covers 90+ AC brands; if the actual unit isn't supported, fall back to capture-and-replay using an IR receiver to record the raw pulse train from the physical remote |
| Bridge hub (fallback path only) | Raspberry Pi Zero 2 W or 3B+ | Only runs a local broker + bridge; doesn't need Pi 4/5-level compute |

## 5. Connectivity architecture

No central hub is required for the default case — ESP32 devices connect straight to the campus enterprise wifi and publish to the central broker. This was chosen over the originally-proposed single-Raspberry-Pi-hub-per-room design because the campus network's WPA2/WPA3-Enterprise (802.1X) wifi is directly reachable by ESP32's native enterprise wifi support.

**Unverified prerequisite:** a device on that campus wifi must be able to route to the VPS (not just get an IP). This must be tested — connect a laptop to the wifi and ping/curl the VPS — before any further hardware purchase or deployment. If blocked, it needs a firewall/VLAN conversation with campus IT, not a device-side workaround.

**Dual connectivity path:**

- **Default — direct wireless:** ESP32 → campus 802.1X wifi (TLS) → central MQTT broker on the VPS directly.
- **Fallback — wired bridge, only where wireless genuinely struggles** (e.g. the ATS module mounted near/inside metal switchgear): sensor module wired to a local Raspberry Pi → Pi runs its own Mosquitto broker → configured as an MQTT bridge (QoS 1, persistent session/`cleansession false`) forwarding to the same central broker. This gives store-and-forward buffering during a backhaul outage, which the direct-wireless path doesn't get for free.

The bridge connects to the central broker as just another authenticated TLS client on port 8883 — no change to the broker's own configuration is needed to support this path. Both paths converge on the identical topic namespace, so the backend and dashboard don't need to know or care which path a given room uses.

Decision rule: **use direct-wireless by default; only fall back to the Pi-bridge path where RF conditions actually require it.** Do not deploy the Pi path uniformly across all rooms — it adds operational burden (another device to maintain, patch, and monitor) with no benefit in rooms where direct-wireless already works.

## 6. MQTT design

**Broker:** Mosquitto on the VPS. Already built and verified in testing — TLS listener on 8883 for external clients (devices, bridges), localhost-only plaintext listener on 1883 for same-host backend services, no anonymous connections.

**Authentication & authorization:** every client (device, bridge, or backend service) has its own username/password, and an ACL file restricts each credential to only the topics it should touch — enforced at the broker, not just trusted at the application layer. This is the concrete implementation of the Authorization leg of AAA, and it doubles as a device-level Accounting trail via broker logs (which credential touched which topic, and when).

**Topic structure:** `<room>/<module>/<metric>`

| Topic | Direction | Example payload |
|---|---|---|
| `serverroom/temp/value` | device → broker | `{"celsius": 23.5, "ts": 1234567890}` |
| `serverroom/temp/status` | device → broker (retained) | `online` / `offline` |
| `serverroom/ats/status` | device → broker | `{"source": "PLN", "fault": false}` |
| `serverroom/ac/state` | device → broker | `{"power": "on", "setpoint": 22}` |
| `serverroom/ac/cmd` | broker → device | `{"power": "on", "setpoint": 22}` |
| `<room>/<module>/config` | broker → device (retained) | e.g. `{"interval_ms": 5000}` |
| `<room>/<module>/config/ack` | device → broker | applied config version, confirms receipt |
| `discovery/<mac>` | device → broker (retained, birth message) | MAC, firmware type, firmware version |

**Device presence:** each device sets Last Will and Testament to publish `offline` (retained) on its own status topic, and publishes `online` (retained) right after connecting — so the broker announces a dead/disconnected device automatically, and any dashboard client that just (re)connected gets the last-known state immediately via the retained flag.

**QoS:** QoS 1 (at-least-once) for all reading and command topics, including the Pi bridge connection, so a brief reconnect doesn't silently drop a message. The backend's ingest logic tolerates the occasional duplicate delivery this can cause — acceptable for monitoring data, not worth extra dedup engineering at this scale.

**Remote configuration:** device-side settings (sampling interval, calibration offset, AC schedule, log verbosity) are pushed via retained config topics, with the device acking back the version it actually applied so the dashboard can distinguish "sent" from "confirmed." Alert **thresholds are explicitly excluded from this mechanism** — they live server-side only, evaluated at ingest, to avoid two disagreeing sources of truth.

## 7. Roles (AAA)

| Role | Permissions |
|---|---|
| Admin | Full control: user management, device pairing/reassignment, threshold configuration, everything Operator can do |
| Operator | Day-to-day: acknowledge/adjust thresholds, send AC commands (dashboard and via linked Telegram account) |
| Viewer | Read-only dashboard access |

**Accounting** is satisfied by two layers: the MQTT broker's per-credential logs (which device touched which topic), and application-level logging of admin/operator actions (pairing, reassignment, threshold changes, AC commands issued via dashboard or Telegram).

## 8. Alerting

- **Evaluation happens server-side**, the moment a reading's JSON lands at the backend — this is the source of truth, not something duplicated into device firmware. This keeps threshold changes instant (no re-flash), keeps one source of truth in Postgres, and allows retroactive recalculation of historical severity if a threshold is later changed.
- **Local fail-safe, independent of the above:** each device also carries one hardcoded, rarely-changed absolute safety limit (e.g. trip a local buzzer/relay past a hard temperature ceiling), fully decoupled from network/server state. This is a last-resort safety net, not the real alerting system, for the case where the network path itself has failed.
- **Hysteresis + debounce** on every threshold to prevent alert flapping near the boundary: separate enter/clear values (default 1°C gap) and N-consecutive-readings confirmation (default 3) before a state change registers. Both values are configurable per device/parameter alongside the threshold itself, on the same pairing-tab settings screen.
- **No acknowledge/resolve state for now** — alerts are fire-and-log. This was a deliberate simplification given uncertainty about the professor's exact expectations; it's an additive change (add a `status` column) if it's needed later, not a redesign.
- **Telegram push is configurable**, per device/threshold, off by default — an admin/operator opts specific alerts into pushing to the Hermes Telegram channel.

## 9. Device pairing & topology

- Devices self-announce on connect via a retained birth message on `discovery/<mac>` (MAC address + firmware type). The backend upserts these into an "unpaired devices" list.
- An Admin pairs a device: assigns a display name, room, position on the floor plan, and threshold settings. Device-asserted data (MAC, firmware type) is trusted as identity; room/location is always an explicit admin action, never inferred from anything the device claims about itself.
- **Topology:** the floor plan is a custom-recreated SVG/image (not a GIS library — unnecessary complexity for a single building). Each paired device's position is stored as x/y percentage coordinates in Postgres. The dashboard renders the image, overlays markers colored by current status (pulled from Redis for live state), and clicking a marker drills into that device's detail/graph view.

## 10. Real-time data layer

1. A backend service subscribes to the MQTT broker, validates every incoming payload against a schema (Zod) before it touches storage — malformed payloads are rejected and logged, never silently accepted.
2. Valid readings are written to Postgres (full history) and to Redis as the latest-value cache (`device:<mac>:latest` or similar).
3. The same write publishes on a Redis pub/sub channel; a WebSocket server subscribed to that channel pushes the update to connected dashboard clients in real time.
4. This design is horizontally scalable: multiple backend instances can all subscribe to the same Redis channel and push to whichever clients they're holding — relevant once the system grows toward the 8-selasar future.

## 11. Security

- TLS on every hop that leaves a machine you control: device↔broker, bridge↔broker, browser↔dashboard. The Pi's own local wired listener (sensor↔Pi) can skip TLS if physically isolated, but not authentication.
- Dashboard sessions use httpOnly secure cookies, not a JWT stored in `localStorage` (which is readable by any injected script).
- RBAC is enforced server-side on every API route — hiding a button in the React UI is a UX nicety, not a security boundary.
- WebSocket connections carry the same auth context as the REST API — an unauthenticated client must not be able to open a socket and receive live sensor data for free.
- Postgres and Redis are bound to localhost only, never exposed on the VPS's public interface.
- Grafana connects to Postgres with a read-only role, not full credentials.
- Secrets (DB password, MQTT credentials, Telegram bot token, session signing key) live in environment variables / systemd env files, never hardcoded or committed to a repository.
- Rate limiting on the login endpoint and any bot-facing endpoint, to blunt brute-force attempts.
- ESP32 flash encryption / secure boot is an optional hardening step, worth it mainly for rooms with weaker physical access control — not mandated for all devices.

## 12. Hermes — Telegram agent

- **Capabilities:** read (ask about current/historical room or device condition) and limited write (AC on/off/setpoint, threshold adjustment) — write actions gated to accounts linked to an Operator or Admin role.
- **Confirmation:** every write action requires an explicit confirmation via a Telegram inline button before executing. This is a deliberate cost control too — the confirmation step is a button tap (a Telegram callback), not another LLM call.
- **Identity linking:** self-service — a user generates a short-lived code on the dashboard and sends it to the bot to link their Telegram account to their dashboard role. Chosen over admin-manual-linking despite the extra build cost, because it's worth it if/when this scales beyond a handful of people.
- **Distribution:** a single shared Telegram channel for now. The subscription model is still designed as a first-class user↔device/room mapping in the schema, so per-user filtering later is a data change, not a redesign.
- **Guardrails:** a per-user rate cap on LLM calls (cost control against spam or accidental loops), and every write action re-checks the requester's role server-side at the API layer at the moment of execution — never trusting the Telegram-side link record alone.
- **Architecture:** the agent calls a small internal API (read-only-plus-scoped-write), not raw DB/Redis access. The same API backs the public dashboard — no duplicated business logic between the two consumers.

## 13. Data retention & backups

- Raw readings are kept indefinitely in Postgres. At the current planned scale (roughly 8 devices publishing every 30s ≈ ~23,000 rows/day, ~8.4M rows/year) this is trivial for plain Postgres for years; TimescaleDB (a drop-in Postgres extension, not a new database) is the known upgrade path if query performance ever becomes an issue at much larger scale.
- Index on `(device_id, timestamp)` at minimum, since the readings table is append-only and ever-growing.
- A `pg_dump` cron job backs up the database to storage off the VPS — the "keep forever" decision only holds if a single disk failure can't erase the whole history.

## 14. Observability

- Prometheus + node_exporter monitor the VPS itself (CPU, RAM, disk, Mosquitto process health) — a different question from what the sensors answer, and one a professor is likely to ask about directly.
- Structured (JSON) logs from the backend service, with log rotation so a multi-year deployment doesn't quietly fill the disk.
- A `/healthz` endpoint on the backend for uptime monitoring.
- Grafana, connected read-only to Postgres, provides production-grade historical dashboards, alerting rules, and export for the "data logging and grafik" requirement — can also visualize the Prometheus VPS metrics as a separate dashboard.

## 15. Deployment

- Docker Compose bundles the backend, Postgres, Redis, Grafana, and Caddy (reverse proxy + automatic TLS via Let's Encrypt) — reproducible, and a real answer to "who maintains this after the current team graduates."
- Mosquitto stays a native systemd service on the VPS — it's already built, configured, and verified working; no reason to re-containerize it.
- Firewall (ufw) exposes only what's needed: 443 (dashboard HTTPS), 8883 (MQTT TLS), and SSH — Postgres and Redis are never opened externally, containerized or not.

## 16. Tech stack

- **Frontend:** React + Vite
- **Database:** PostgreSQL (TimescaleDB as a known future upgrade path)
- **Cache / real-time fan-out:** Redis (latest-value cache + pub/sub for WebSocket updates)
- **Validation:** Zod (schema-validate every MQTT payload at ingest)
- **Broker:** Mosquitto (TLS, per-device auth, ACL, MQTT bridge for the Pi fallback path)
- **Dashboards/alerting (internal/ops):** Grafana
- **Reverse proxy / TLS:** Caddy
- **Observability:** Prometheus + node_exporter
- **Deployment:** Docker Compose (app layer) + native systemd (Mosquitto)
- **Backend runtime:** not yet finalized — see Open questions

## 17. Open questions / next steps

These are genuinely unresolved as of this spec and should not be read as decided:

- **Ecolab's exact monitoring parameters** — Pak Isnan's request was raised early on but the specifics (temperature only, or additional parameters) were never confirmed. Needs a direct follow-up before the Ecolab BOM/module design is finalized.
- **Room 3 and Room 4 identity** — which two additional rooms, beyond the server room and Ecolab, make up the initial 4-room scope.
- **Which specific rooms need the Raspberry Pi bridge path** — the decision rule (RF-hostile spots only) is settled, but the actual room list depends on an on-site RF survey that hasn't happened yet.
- **Campus wifi → VPS reachability** — must be verified (ping/curl test from a device on that wifi) before hardware purchase or deployment proceeds; this is the single biggest go/no-go variable in the whole connectivity design.
- **ATS sensing tier** — PZEM-004T v3 is recommended as the default for its power-quality data and production-grade credibility, but the cheaper optocoupler-only alternative was never explicitly ruled out by the user.
- **Backend runtime** — Node.js/TypeScript (shares types with the React frontend) vs. Python/FastAPI (if the team is more fluent there) — a team-fluency call, not yet made.
- **Exact AC brand/model** — needs to be checked against IRremoteESP8266's supported list; if unsupported, plan falls back to capture-and-replay.
- **Alert acknowledge/resolve flow** — explicitly deferred (fire-and-log only, for now) pending clarity on what the professor actually expects; flagged as an easy additive change if needed later.

## 18. Explicitly out of scope for this build

- Building-wide 8-selasar rollout and multi-hub central management — the architecture accommodates it, but it is not being built now.
- Multi-VPS / broker clustering / database replication for high availability — not realistic or necessary given a single allocated VPS and the project's actual scale; the accepted trade-off is a single VPS with auto-restart and health monitoring, not full HA.
