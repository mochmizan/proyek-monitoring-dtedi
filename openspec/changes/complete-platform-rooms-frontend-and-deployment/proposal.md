## Why

Three changes have shipped: backend hardening + ATS command relay, user auth/RBAC, and field firmware alignment. What remains to reach feature-complete, consolidated into one change per request: the rooms/gateway/device-pairing/floor-map/alerts backend (nothing built yet — `event_log` still has nothing writing to it), the frontend integration (the mockup still runs entirely on Zustand-simulated fake data), the edge daemon's missing offline resilience (HubBrain silently drops telemetry if the VPS link drops — the original brainstorm's store-and-forward design was never implemented), and the actual VPS deployment. This change also folds in two fixes surfaced during the firmware alignment review: replacing the NaN-to-zero sensor-error sentinel with skip-on-error, and generalizing the edge command dispatcher's topic resolution so it isn't hardcoded per device type.

## What Changes

- Add `rooms` and floor-plan-marker storage; add device pairing (self-discovery already exists via `receive_unapproved_alert` — this adds the admin-facing pairing workflow: assign name, room, marker position, initial thresholds).
- Add per-device configurable warning/critical thresholds, hysteresis, and debounce; add server-side threshold evaluation on telemetry ingest that writes to `event_log`; add an alerts list/filter API.
- Add frontend integration: replace the Zustand mock store's simulated data with real TanStack Query calls against HubGate; wire the login page and route guards to the real `/api/auth/*` endpoints; poll for live telemetry (2–5s interval) instead of the mockup's client-side random-walk simulation.
- Add HubBrain offline store-and-forward: a local SQLite WAL cache that buffers telemetry when the HTTPS POST to HubGate fails, and a paced FIFO replay loop when connectivity recovers.
- **Fix (from firmware alignment review)**: replace the AC/temperature nodes' NaN→`0.0` sentinel with skip-publish-this-cycle on sensor read failure, so a sensor fault is never indistinguishable from a real zero-degree reading.
- **Fix (from firmware alignment review)**: generalize HubBrain's command-dispatch topic resolution to derive the downlink topic from the target device's type/`dev_id` rather than a hardcoded ATS-specific topic string, so it also correctly dispatches AC commands and any future device type without repeating the same class of bug.
- Add production deployment: build and serve the frontend as static assets from the same Nginx origin as the API (not a separate origin) — this is a **required** decision, not a preference, because the session cookie is `SameSite=Lax`; browsers do not attach `SameSite=Lax` cookies to cross-origin `fetch`/XHR requests (only to top-level same-method navigations), so a cross-origin frontend would silently fail to authenticate against the API. Local development uses Vite's dev-server proxy for the same reason, not CORS.
- Add a local test environment: a Docker Compose stack (Postgres + Mosquitto) plus mock device publishers, so the entire pipeline — device → broker → HubBrain → HubGate → database → dashboard — can be exercised on a laptop with no physical hardware, before anything touches the VPS or the physical Pi.
- Add a mandatory Raspberry Pi backup step ahead of this change's edge-gateway work: a full SD card image (or at minimum the specific config directories already identified — NetworkManager/hostapd config, Mosquitto config, the HubBrain systemd unit, `.env`, `cert.crt`) must exist and be verified before HubBrain's offline-cache/command-dispatch changes are deployed to the physical Pi.
- Resolve the ATS Wemos-Arduino serial command format conflict: the hardware team's original WhatsApp-specified format (`<SGM,on>`, `<SGM,off>`, `<RST,rst>`, `<M,auto>`/`<M,manual>`) is designated canonical over a later report's differing claim (`<C,SGM_ON>` etc.), since that report's account of a separate firmware file was independently confirmed fabricated — its ATS protocol table is not trusted either without direct code verification.

## Capabilities

### New Capabilities
- `room-and-device-management`: rooms, gateway-room association, and the admin device-pairing workflow.
- `floor-plan-mapping`: floor plan image storage and per-device marker coordinates.
- `alert-threshold-evaluation`: per-device threshold configuration and server-side breach detection/logging.
- `frontend-live-integration`: the dashboard's live-data and auth wiring against real endpoints, replacing simulated mock state.
- `edge-offline-resilience`: HubBrain's local buffering and paced replay when the cloud link is unavailable.
- `production-deployment`: same-origin serving topology and the deployment procedure itself, including the mandatory Pi backup gate.
- `local-test-environment`: a Docker-based local stack and mock publishers letting the full pipeline be exercised without physical hardware or VPS access.
- `ats-serial-protocol-integrity`: resolving the Wemos-Arduino serial command format to a single canonical version, verified against actual code rather than a prior (partly fabricated) summary.

### Modified Capabilities
- `field-node-connection-resilience` (from `align-field-firmware-with-live-hub`): the sensor-failure behavior changes from "publish a sanitized zero value" to "skip publishing this cycle" — this is a refinement of that capability's existing non-blocking-operation intent, not a reversal of it.

## Impact

- **Code**: new backend modules for rooms/pairing/alerts endpoints and models; `edge/main.py` (offline cache + generalized command dispatch); frontend `src/store/appStore.ts` and route files (real queries replacing simulation); `firmware/WEMOS_TS.ino`/`WEMOS_AC.ino` (skip-on-NaN fix); Nginx config (static frontend + API same-origin).
- **Database**: new `rooms`, `device_pairing_config` (thresholds/hysteresis/debounce), and floor-plan-marker columns/tables; `event_log` gets its first real writer.
- **Edge storage**: new local SQLite file on the Raspberry Pi for the offline cache (separate from any cloud database).
- **Deployment**: this change includes the actual VPS push — Nginx reconfigured to serve the built frontend alongside the reverse-proxied API, `.env` populated with production values, migrations run against the real production database.
- **Out of scope still**: Telegram push notifications for alerts (mentioned as optional in original scope, not built here), Grafana/analytics dashboard, multi-VPS HA.
