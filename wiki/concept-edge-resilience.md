---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubbrain-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-command-path.md, wiki/entity-firmware-fleet.md, wiki/entity-hubgate-v5.md, wiki/entity-devops-infrastructure.md]
sources: [hub/main.py, hub/requirements.txt, hub/test_edge_resilience.py, hub/AGENTS.md, docs/PRODUCTION_DEPLOYMENT_GUIDE.md]
updated: 2026-09-12
---

# Edge Resilience & Offline Buffering

Edge resilience in the SMSB architecture guarantees that telemetry ingestion, local ATS switching, and environmental monitoring remain continuous during campus WAN outages, server reboots, network congestion, and sudden power fluctuations. The edge gateway daemon (`HubBrain V5` running on a Raspberry Pi 4) acts as an autonomous store-and-forward buffer between the local fleet and the cloud backend (`HubGate V5`).

```
  +-------------------------+
  |    Local MQTT Fleet     |
  |  (ATS, TS, AC on Wi-Fi) |
  +------------+------------+
               |
               v
  +-------------------------+
  |   paho-mqtt on_message  |
  +------------+------------+
               |
        Is MAC Whitelisted?
         /           \
       No             Yes
       /               \
      v                 v
[Report to        Direct HTTPS POST
/unapproved]        (Timeout: 5s)
                    /          \
              Success           Failure (Net error / 5xx)
                /                  \
               v                    v
          [Delivered]      +-------------------------------+
                           |      SQLite WAL Cache         |
                           |       (edge_cache.db)         |
                           |   MAX_PENDING_ROWS = 20000    |
                           |       7-Day Retention         |
                           +---------------+---------------+
                                           |
                                    Replay Thread
                               (Every 5s, 0.35s pacing,
                                 batch 25, FIFO order,
                                stamps _hub_created_at)
                                           |
                                           v
                             +---------------------------+
                             |    HubGate HTTPS API      |
                             +---------------------------+
```

---

## 1. Network Boundary Isolation & Dual-Interface Routing

Each Raspberry Pi 4 edge gateway isolates traffic between two separate network segments:
1. **Local IoT Fleet Bubble (`wlan0`)**:
   - Access point broadcast via `hostapd` and `dnsmasq` (hidden SSID `smsb-iot`).
   - Subnet: `192.168.72.242/24` (static IP assigned to Pi).
   - Hosts local Mosquitto MQTT broker (`localhost:1883`, credentials `hubadmin`).
   - Completely isolated from campus IT traffic; field nodes communicate strictly with this broker.
2. **Campus LAN / WAN Uplink (`eth0`)**:
   - Upstream link to central server (`HubGate V5`).
   - Static IP `10.33.102.10/24` via gateway `10.33.102.254`.
   - Synchronizes time with campus NTP server (`10.33.102.172`) using `chrony 4.8` to compensate for the Raspberry Pi's lack of a battery-backed hardware RTC.
   - **Campus Inter-VLAN Isolation**: Inbound access from campus wireless networks (`UGM-Hotspot`, `UGMSecure`) is blocked by DSSDI core firewall inter-VLAN routing rules. Access requires DTEDI wired Ethernet, UGM Campus VPN (`vpn.ugm.ac.id`), or Tailscale.
   - **Remote Hardware Testing Tunnel**: Off-campus or wireless hardware developers reach the Pi Mosquitto broker by establishing an SSH local forwarding tunnel through the central VPS (`ssh -N -L 1883:10.33.102.10:1883 genset@100.108.98.30`), authenticating on `localhost:1883` as `hubadmin` (`414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1`).

---

## 2. Ingestion Filtering & Zero-Backpressure Invariant

### 2.1 MAC Address Whitelist & Registry Synchronization
- **In-Memory Cache**: `WHITELIST_DEVICES` (set of authorized MAC strings) and `DEVICE_REGISTRY` (metadata mapping MAC to `dev_name`, `dev_type`, and `hub_name`) protected by `DEVICE_REGISTRY_LOCK`.
- **Periodic Synchronization**: The `sync_whitelist()` worker thread queries `GET /api/devices` every 30 seconds with authentication headers (`X-Hub-ID`, `X-Hub-Key`).
- **Unapproved Device Discovery**: Telemetry received from unauthorized MAC addresses is discarded from direct forward pipelines. Unapproved devices are reported to `POST /api/iot/unapproved` (debounced via `REPORTED_UNAPPROVED_MACS` to at most once per 5 seconds per MAC) for dashboard discovery.

### 2.2 Zero-Backpressure Invariant
Live incoming telemetry is never held behind offline backlogs when upstream connectivity is healthy:
- In `on_message()`, whitelisted telemetry immediately attempts a synchronous direct forward:
  ```python
  response = requests.post(SERVER_URL, json=data, headers=get_hub_headers(), verify=TLS_CERT_PATH, timeout=5)
  ```
- If direct forward succeeds (HTTP 200/201), the payload bypasses disk storage entirely.
- Offline cache buffering occurs strictly upon direct forward failure (network timeout, connection drop, or HTTP 5xx). The replay worker drains backlogs independently in the background.

---

## 3. SQLite Write-Ahead Logging (WAL) Storage Architecture

When direct forwarding fails, telemetry payloads are buffered into `edge_cache.db`.

### 3.1 Schema & Indexing
```sql
CREATE TABLE IF NOT EXISTS pending_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_telemetry(created_at);
```

### 3.2 Performance & MicroSD Endurance PRAGMAs
Database connections created via `get_db_conn()` execute dedicated PRAGMAs:
- `PRAGMA journal_mode = WAL;`: Write-Ahead Logging allows concurrent readers and writers without lock contention.
- `PRAGMA busy_timeout = 5000;`: Waits up to 5,000 ms before raising database busy exceptions.
- `PRAGMA synchronous = NORMAL;`: Ensures crash resistance against power cuts while eliminating `fsync` on every transaction, dramatically reducing microSD write wear.
- `PRAGMA temp_store = MEMORY;`: Keeps temporary tables and indices in RAM.

### 3.3 File Descriptor Safety
Connection lifecycles are strictly managed via context manager:
```python
@contextmanager
def get_db_conn(db_path: str = None):
    conn = sqlite3.connect(target_path, timeout=5.0)
    # Apply PRAGMAs...
    try:
        yield conn
    finally:
        conn.close()
```
This guarantees deterministic connection closing, eliminating file descriptor leaks (`EMFILE: Too many open files`).

---

## 4. Bounded Queue Capacity & Retention Policies

Unchecked queue growth on edge hardware risks microSD exhaustion. HubBrain V5 enforces strict bounding:

1. **Queue Capacity Limit (`MAX_PENDING_ROWS = 20000`)**:
   - The pending queue is capped at 20,000 records (~6–10 MB disk footprint).
   - On overflow, `enqueue_pending_telemetry()` prunes the oldest records in strict FIFO order:
     ```sql
     DELETE FROM pending_telemetry
     WHERE id IN (
         SELECT id FROM pending_telemetry
         ORDER BY id ASC LIMIT :overflow
     );
     ```
2. **TTL Eviction (7 Days)**:
   - On each enqueue operation, records older than 7 days (`created_at < time.time() - 604800`) are pruned. Telemetry older than 7 days is considered stale for alerting.

---

## 5. Paced Backlog Replay & Flow Control

When network connectivity to HubGate V5 is restored, the `replay_backlog_thread` daemon drains the backlog:

| Parameter | Value | Purpose |
|---|---|---|
| `REPLAY_INTERVAL` | 5.0 seconds | Polling cycle when queue is empty |
| `REPLAY_BATCH_SIZE` | 25 records | Maximum records drained per transaction batch |
| `REPLAY_PACING_DELAY`| 0.35 seconds | Sleep delay between consecutive HTTP POSTs |

### 5.1 Upstream Rate-Limit & Server Protection
With `REPLAY_PACING_DELAY = 0.35`, maximum replay rate is capped at ~2.85 requests per second (~171 requests per minute). This prevents:
- Overloading backend PostgreSQL connection pools on resource-bounded VPS instances (preserving headroom for co-tenancies like CTFd on the 4GB allocation profile).
- Triggering HTTP 429 Too Many Requests rate-limiting.
- Flooding the alert engine with burst anomalies.

---

## 6. Timestamp Preservation (`_hub_created_at`)

When records are buffered during WAN outages, historical fidelity must be preserved:
1. **The Issue**: A naive server stamping records with `datetime.now()` upon receipt causes 12 hours of outages to compress into a single burst, causing false alert storms and corrupted trend charts.
2. **The Mechanism**: In `replay_backlog_batch()`, the edge gateway checks each record and injects the original enqueue epoch:
   ```python
   if "_hub_created_at" not in payload_dict and "HUB_TS" not in payload_dict:
       payload_dict["_hub_created_at"] = float(created_at)
   ```
3. **Backend Ingestion**: The central server (`server/app/routers/iot.py`) inspects `_hub_created_at` and assigns it as `event_time` in PostgreSQL, reconstructing the true historical timeline.

---

## 7. Failure Modes & Recovery Matrix

| Condition / Status | Upstream Response | Gateway Action | Database Resolution |
|---|---|---|---|
| Link Healthy | HTTP 200 / 201 | Direct forward successful | Record deleted from SQLite (`DELETE WHERE id = :id`) |
| Server Rate Limited | HTTP 429 | Backoff sleep for 15s; abort batch | Records retained in SQLite for subsequent retry |
| Malformed / Invalid Schema | HTTP 400, 403, 422 | Server rejects unprocessable payload | Record quarantined and deleted from SQLite to prevent FIFO stall |
| Corrupted JSON in Cache | `json.JSONDecodeError` | JSON unparseable | Record deleted immediately from SQLite |
| Network Outage / DNS Loss | `requests.exceptions.RequestException` | Upstream unreachable; pause replay | Records retained in SQLite; replay sleeps `REPLAY_INTERVAL` |
| Server Internal Error | HTTP 500, 502, 503, 504 | Upstream degraded; pause replay | Current batch aborted; records retained for next cycle |

---

## 8. Production-Readiness Gap Analysis

The edge resilience subsystem exhibits five key technical deficiencies requiring refactoring:

### 8.1 MicroSD Card Disk Full Vulnerability
- **Defect**: No disk space inspection (`shutil.disk_usage()`) is performed before writing to SQLite.
- **Failure Mode**: When journald logs or system dumps consume root filesystem space, SQLite writes fail with `sqlite3.OperationalError: disk I/O error`, causing unhandled exceptions and halting the edge gateway.
- **Remediation**: Check available disk space before queueing; if free disk space is below 100 MB, drop incoming payloads to avoid crashing, and alert the central server.

### 8.2 SQLite WAL Corruption Resilience
- **Defect**: Startup initialization (`init_db()`) does not execute database integrity checks (`PRAGMA quick_check;`).
- **Failure Mode**: Sudden power cuts during disk writes can leave corrupted `-wal` files, causing `DatabaseError: database disk image is malformed` and permanently stalling replay workers.
- **Remediation**: Execute `PRAGMA quick_check;` on startup. If corrupted, quarantine `edge_cache.db` to `edge_cache_corrupt_{epoch}.db`, create a clean database, and report the event.

### 8.3 TLS Certificate Validation & Pinning
- **Defect**: `main.py` suppresses certificate warnings via `urllib3.disable_warnings(InsecureRequestWarning)` and only verifies file existence without inspecting certificate expiration dates.
- **Failure Mode**: When `cert.crt` expires on the Raspberry Pi, all upstream transmission fails silently, filling the offline queue until disk overflow occurs.
- **Remediation**: Implement certificate expiration validation on startup and emit alert warnings 30 days prior to expiry.

### 8.4 Systemd Watchdog Integration (`sd_notify`)
- **Defect**: `hubbrain.service` runs as a basic systemd unit without watchdog monitoring.
- **Failure Mode**: Thread deadlocks, socket hangs, or memory leaks leave the process frozen while systemd considers it healthy.
- **Remediation**: Configure `WatchdogSec=30` in the service unit and send `systemd.daemon.notify("WATCHDOG=1")` heartbeats from the main thread loop.

### 8.5 Edge Observability & Heartbeat Telemetry
- **Defect**: Gateway health metrics (queue depth, free disk space, process uptime, memory) are only logged to stdout.
- **Failure Mode**: Cloud operators cannot monitor edge backlog buildup or detect failing gateway hardware.
- **Remediation**: Implement a periodic heartbeat transmission (`POST /api/hub/heartbeat`) reporting edge queue depth and operational health.
