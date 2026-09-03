---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-edge-resilience.md, wiki/concept-telemetry-pipeline.md, wiki/concept-command-path.md, wiki/entity-ats-firmware-chain.md, wiki/entity-firmware-fleet.md, wiki/entity-hubgate-v5.md]
sources: [hub/main.py, hub/AGENTS.md, hub/requirements.txt, hub/test_edge_resilience.py]
updated: 2026-09-03
---

# HubBrain V5 (hub/)

HubBrain V5 is the single-file edge gateway daemon (`hub/main.py`) running on Raspberry Pi 4 units deployed across server and power rooms. It bridges local MQTT traffic (`hs109rs/#`) to the central HubGate HTTPS API (`/api/iot`), manages downlink command delivery to field microcontrollers, buffers offline telemetry in a bounded SQLite WAL, and enforces MAC whitelisting.

---

## 1. Process & Thread Architecture

HubBrain V5 executes four asynchronous daemon worker threads alongside the primary lifecycle loop:

| Thread Name | Function | Cycle / Trigger | Operations & Network Interactions |
|---|---|---|---|
| **Whitelist Sync** | `sync_whitelist()` | Periodic (30s) | Queries `GET /api/devices` with `X-Hub-ID` and `X-Hub-Key`. Updates in-memory `WHITELIST_DEVICES` (set of MAC strings) and `DEVICE_REGISTRY` (metadata mapping) under `DEVICE_REGISTRY_LOCK`. |
| **Command Poller** | `poll_commands()` | Periodic (2s) | Polls pending commands via `GET /api/hub/commands`. Resolves MQTT downlink topic dynamically (`{hub_name}/{dev_type}/command`), validates payloads by device type, dispatches via local MQTT broker, and acknowledges delivery via `POST /api/hub/commands/{id}/delivered`. |
| **WAL Replay Worker** | `replay_backlog_thread()` | Periodic (5s) | Drains offline SQLite cache in strict FIFO batches of 25 (`REPLAY_BATCH_SIZE`). Applies mandatory 0.35s pacing delay (`REPLAY_PACING_DELAY`) between records (~2.85 req/s). Injects original enqueue timestamp as `_hub_created_at` epoch. |
| **MQTT Client Loop** | `paho.mqtt.client.loop_start()` | Event-driven | Subscribes to `hs109rs/#` on local Mosquitto broker (`localhost:1883`, credentials `hubadmin`). Uses `paho-mqtt==2.2.1` with `CallbackAPIVersion.VERSION1`. Processes telemetry in `on_message()`. |
| **Main Thread** | `main()` | Continuous / Signal | Coordinates startup, database schema initialization (`init_db()`), TLS certificate preflight (`verify_tls_cert_file()`), thread spawning, and interactive CLI (`--interactive`) or headless daemon sleep loop. |

All central server calls enforce a strict `timeout=5` and require authentication headers generated via `get_hub_headers()`:
- `Content-Type`: `application/json`
- `X-Hub-ID`: Configured Hub identifier (e.g. `hs109rs-hub-01`).
- `X-Hub-Key`: Cryptographic shared secret configured via environment variable `HUB_KEY`.

---

## 2. Ingestion & Filtering Contract

### 2.1 Whitelisting & Filtering
1. Incoming MQTT messages arrive on `hs109rs/#` (topics: `hs109rs/ts/data`, `hs109rs/ac/data`, `hs109rs/ats/data`).
2. The payload is parsed as JSON. Device MAC address is extracted from `data["DEV_ID"]`.
3. If `DEV_ID` is present in `WHITELIST_DEVICES` or `DEVICE_REGISTRY`:
   - Direct forward is attempted via `POST SERVER_URL` (`/api/iot`).
   - If forward fails (network unreachable or HTTP 5xx), the payload is enqueued into `edge_cache.db`.
4. If `DEV_ID` is **not** whitelisted:
   - The message is dropped with `[FILTER BLOCK]`.
   - The device is reported to `POST /api/iot/unapproved` for discovery in the web dashboard (debounced to at most once every 5 seconds per MAC via `REPORTED_UNAPPROVED_MACS`).

### 2.2 Direct Forwarding Invariant
Live telemetry is never blocked by or queued behind offline backlogs when upstream connectivity is healthy. Synchronous direct forwarding is attempted first; buffering is strictly a failover mechanism (see [concept-edge-resilience.md](concept-edge-resilience.md)).

---

## 3. Command Routing & Downlink Validation

Downlink commands fetched from `GET /api/hub/commands` are dynamically routed to local devices:

### 3.1 Dynamic Topic Resolution (`derive_command_topic`)
The downlink topic is formatted as `{hub_name}/{dev_type}/command`:
- Resolves device metadata from `DEVICE_REGISTRY`.
- If device is uncached, infers type from payload structure:
  - Keys `target`, `action`, `AC_NUMBER`, `AC_COMMAND` -> `ac`
  - Keys `mode`, `start_genset`, `reset` -> `ats`
- Extracts base `hub_name` from `HUB_ID` (e.g., `hs109rs-hub-01` -> `hs109rs`).

### 3.2 Payload Validators
- **AC Payload Contract (`validate_ac_payload`)**:
  - `target` or `AC_NUMBER` must be `"AC1"` or `"AC2"`.
  - `action` or `AC_COMMAND` must be `"ON"`, `"OFF"`, `"SET_TEMP"`, or regex `"TEMP <16-30>"`.
  - Rejects out-of-range temperatures (<16 or >30) or invalid target units.
- **ATS Payload Contract (`validate_ats_payload`)**:
  - Requires at least one valid key: `mode` (`"auto"` or `"manual"`), `start_genset` (`"on"` or `"off"`), or `reset` (`"rst"`).

---

## 4. Offline WAL Queue Contract (`edge_cache.db`)

- **Engine**: SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL;`).
- **PRAGMAs**: `busy_timeout = 5000;`, `synchronous = NORMAL;`, `temp_store = MEMORY;`.
- **Concurrency & FD Safety**: Governed via `get_db_conn()` context manager guaranteeing connection closure in `finally` blocks.
- **Queue Limits**: Bounded capacity `MAX_PENDING_ROWS = 20000`. Oldest records are pruned in FIFO order on overflow.
- **Data Retention**: 7-day TTL (`created_at < time.time() - 604800`) cleaned up on every enqueue.
- **Timestamp Stamping**: Injects `_hub_created_at = float(created_at)` into JSON payload prior to replaying so HubGate V5 reconstructs true historical time series.

---

## 5. Network & Hardware Configuration

- **Fleet Wireless Access Point (`wlan0`)**: Broadcasts hidden WPA2 SSID `smsb-iot` at `192.168.72.242/24` using `hostapd` and `dnsmasq`. Dedicated exclusively to ESP8266 node telemetry.
- **Campus Uplink (`eth0`)**: Static IP `10.33.102.10/24` via gateway `10.33.102.254`. Connects to central server and campus NTP.
- **Time Synchronization**: The Raspberry Pi lacks an onboard hardware RTC battery. Timekeeping is maintained by `chrony 4.8` tracking campus NTP server `10.33.102.172` with `makestep` enabled to correct clocks upon cold boot before database transactions occur.
- **TLS Pinning**: Upstream HTTPS requests pin the server certificate via `verify=TLS_CERT_PATH` (`cert.crt`). Startup fails immediately if `TLS_CERT_PATH` is missing or 0 bytes.

---

## 6. Production-Readiness Gap Analysis

The following technical deficiencies must be addressed to achieve production-grade certification:

1. **MicroSD Card Disk Full Resilience**:
   - *Gap*: `main.py` performs no free disk space checks (`shutil.disk_usage`) before writing to SQLite.
   - *Risk*: A full filesystem triggers unhandled `sqlite3.OperationalError: disk I/O error` exceptions, causing the gateway process to crash.
   - *Remediation*: Implement a disk guard threshold (e.g., 100 MB free space required) and alert server when storage is exhausted.
2. **SQLite WAL Corruption Recovery**:
   - *Gap*: No runtime verification of database integrity (`PRAGMA quick_check;`).
   - *Risk*: Dirty shutdowns during power failure can corrupt WAL indexes, blocking replay permanently.
   - *Remediation*: Add automated database verification on boot; quarantine corrupted `.db` files and recreate the schema automatically.
3. **Systemd Watchdog Integration (`sd_notify`)**:
   - *Gap*: The systemd service `hubbrain.service` runs as a simple process without watchdog pings.
   - *Risk*: Thread deadlocks or frozen network sockets remain running indefinitely without systemd detection.
   - *Remediation*: Enable `WatchdogSec=30` in the service unit and issue `systemd.daemon.notify("WATCHDOG=1")` heartbeats in the main thread loop.
4. **Certificate Expiration Monitoring & Fingerprint Pinning**:
   - *Gap*: Relies on basic file existence; does not check certificate validity expiration dates and suppresses SSL warnings.
   - *Risk*: Silent certificate expiration halts all upstream data transmission without operational alerts.
   - *Remediation*: Validate certificate expiration at boot and emit warning metrics 30 days prior to expiry.
5. **Edge Observability Telemetry**:
   - *Gap*: Edge metrics (queue depth, disk usage, memory, dropped unapproved packets) are written only to standard output.
   - *Risk*: Central monitoring has zero visibility into edge health or backlog buildup.
   - *Remediation*: Implement a periodic `/api/hub/heartbeat` telemetry transmission from each gateway.
