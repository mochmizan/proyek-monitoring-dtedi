## 1. Database

- [x] 1.1 Add `rooms` table (id, name unique, created_at)
- [x] 1.2 Add `hub_id` FK column on `rooms` (or a join table) to associate a gateway with a room
- [x] 1.3 Add `room_id` FK on `dev_table` (nullable — unpaired devices have no room)
- [x] 1.4 Add `device_threshold_config` (dev_id FK, warning, critical, hysteresis, debounce_seconds)
- [x] 1.5 Add floor plan marker fields (either columns on `dev_table` or a small join table): `marker_x`, `marker_y` (0–100)
- [x] 1.6 Add a `floor_plan_image_path` column on `rooms`
- [x] 1.7 Confirm `event_log` schema fits alert records (device, severity, value, threshold, timestamp, resolved_at) — extend if needed
- [x] 1.8 Apply via the existing additive-migration pattern in `init_sqlv5.py`

## 2. Rooms & device pairing backend

- [x] 2.1 `POST/GET/PATCH/DELETE /api/rooms` (admin-only for write, any authenticated role for read); reject delete while devices are assigned
- [x] 2.2 `POST /api/gateways/{hub_id}/room` — associate a hub with a room (admin-only)
- [x] 2.3 `POST /api/devices/{dev_id}/pair` — name, room, initial thresholds, marker position, activates the device (admin-only)
- [x] 2.4 `POST /api/devices/{dev_id}/unpair` — clears room assignment, deactivates, preserves historical telemetry (admin-only)
- [x] 2.5 `GET /api/devices?status=pending` — list self-discovered devices awaiting pairing

## 3. Floor plan & map backend

- [x] 3.1 `POST /api/rooms/{room_id}/floor-plan` — image upload, stored on disk, replaces any prior image for that room
- [x] 3.2 `GET /api/rooms/{room_id}/map` — returns floor plan URL (or "no image" indicator) plus device markers for that room

## 4. Alert threshold evaluation backend

- [x] 4.1 `PUT /api/devices/{dev_id}/thresholds` — set warning/critical/hysteresis/debounce (admin-only)
- [x] 4.2 Wire synchronous threshold evaluation into the existing `receive_iot` ingest path for TS and ATS readings
- [x] 4.3 Implement debounce check (skip logging if the same device/condition alerted within its debounce window)
- [x] 4.4 Implement hysteresis-based resolution (mark `resolved_at` when a reading drops back below warning minus hysteresis)
- [x] 4.5 `GET /api/alerts` with room/device/severity/time-range filters

## 5. Firmware fix (NaN handling)

- [x] 5.1 `WEMOS_TS.ino`: skip `publishData()`/publish call entirely if `isnan(temperature) || isnan(humidity)`, instead of substituting `0.0f`
- [x] 5.2 `WEMOS_AC.ino`: same fix for its `TEMP`/`HUMID` fields

## 6. HubBrain edge fixes

- [x] 6.1 Add a local SQLite file (WAL mode) with a simple `pending_telemetry` table (payload, created_at)
- [x] 6.2 On failed HTTPS forward, write the payload to the local cache instead of dropping it
- [x] 6.3 Add a paced replay loop: on reconnect, read oldest-first, forward, delete on success, small delay between records
- [x] 6.4 Ensure live telemetry is forwarded immediately even while a backlog replay is in progress (don't queue behind the backlog)
- [x] 6.5 Generalize the command-dispatch topic: resolve `{HUB_NAME}/{dev_type}/command` from the target device's known type instead of a hardcoded ATS-specific topic string
- [x] 6.6 Verify AC commands now dispatch correctly through the same generalized path

## 7. Frontend integration

- [x] 7.1 Remove the Zustand telemetry simulator; replace room/device state with TanStack Query hooks against real endpoints
- [x] 7.2 Wire polling (2–5s) on room/device detail views
- [x] 7.3 Wire login page to `POST /api/auth/login`; wire route guards to `GET /api/auth/me`
- [x] 7.4 Wire Settings (rooms, pairing, thresholds) to the new admin endpoints
- [x] 7.5 Wire Map view to `GET /api/rooms/{id}/map`
- [x] 7.6 Wire Alerts page filters to `GET /api/alerts`
- [x] 7.7 Configure Vite dev-server proxy for local development (not CORS) to keep requests same-origin


## 8. Local test environment

- [x] 8.1 Write `docker-compose.yml`: Postgres (official image) + Eclipse Mosquitto (official image, authenticated — mount a `mosquitto.conf` with `allow_anonymous false` and a generated `passwd` file)
- [x] 8.2 Write mock publisher scripts (`paho-mqtt`-based) for TS, ATS, and AC payloads matching the real schemas
- [x] 8.3 Document `.env` values for running HubGate and HubBrain against the local stack
- [x] 8.4 Write the local testing README (start stack, run publishers, run HubGate/HubBrain, expected results)
- [x] 8.5 Verify: mock ATS publish → local HubBrain forward → local HubGate → `ats_data` row appears

## 9. Raspberry Pi backup (gate before any edge deployment)

- [x] 9.1 Take a full SD card image backup of the physical Pi (`dd`/`rpi-clone` or equivalent), or at minimum tar the NetworkManager/hostapd config, `/etc/mosquitto/`, the HubBrain systemd unit, `.env`, and `cert.crt`
- [x] 9.2 Store the backup somewhere off the Pi itself (laptop, external drive, etc.)
- [x] 9.3 Confirm the backup is restorable in principle (verify the image/tar isn't corrupted or empty) before proceeding to deploy any HubBrain changes to the physical device

## 10. Deployment

- [x] 10.1 Build frontend static assets; configure Nginx to serve them and reverse-proxy `/api` to Uvicorn on the same origin
- [x] 10.2 Populate production `.env` with real values; verify no placeholder/example values remain
- [x] 10.3 Run all pending additive migrations against the production database
- [x] 10.4 Deploy backend + frontend to the VPS first; verify against production before touching the Pi
- [x] 10.5 Only after task 9 (backup) is complete: deploy updated HubBrain to the physical Pi
- [x] 10.6 Verify a full pipeline check (device telemetry → dashboard, login, pairing, alert) against production

## 12. ATS serial protocol reconciliation

- [x] 12.1 Open `fixed_wemos_mqtt_raspi.ino`'s actual current command-sending code (not a report summary) and record exactly what it transmits for start-genset, stop, and reset
- [x] 12.2 Open `fsm_w_serial.ino`'s actual current serial command parser and record exactly what it expects to receive for the same commands
- [x] 12.3 Compare both against the canonical format (`<SGM,on>`, `<SGM,off>`, `<RST,rst>`, `<M,auto>`, `<M,manual>`); correct whichever side(s) don't match
- [x] 12.4 Bench test: send each command from the Wemos side (or via serial monitor) and confirm the Arduino responds correctly, not just that the code compiles

## 13. Verification

- [x] 11.1 Test: pairing a pending device assigns room/thresholds/marker and activates it
- [x] 11.2 Test: threshold breach logs an alert; recovery (with hysteresis) resolves it; rapid oscillation within debounce window logs only once
- [x] 11.3 Test: floor plan upload/replace; map endpoint returns "no image" gracefully when none exists
- [x] 11.4 Test: HubBrain offline cache — simulate a forward failure, confirm the record is cached, restore connectivity, confirm paced FIFO replay and cache cleanup
- [x] 11.5 Test: AC command dispatches correctly through the generalized topic resolver
- [x] 11.6 Manual: full frontend walkthrough (login → dashboard → room detail live updates → pairing → map → alerts) against a deployed instance
