---
type: workstream
governed_by: AGENTS.md
links: [wiki/concept-production-readiness.md, wiki/concept-observability-monitoring.md, wiki/entity-devops-infrastructure.md, wiki/entity-deploy-pipeline.md, wiki/entity-hubgate-v5.md]
sources: [deploy/setup_push_deploy.sh, tools/migrate_sqlite_to_postgres.py, docs/runbooks/postgres_cutover_runbook.md, server/databasev5.py, notes/field-ops.md, notes/benchmarks-baseline.md, dashboard/src/lib/chartUtils.ts, dashboard/src/lib/constants.ts]
updated: 2026-09-17
---

# Workstream: Production-Grade Refactoring Roadmap

This workstream establishes an actionable, prioritized refactoring program to transition the SMSB system from Hardened Staging to enterprise Production-Grade Tier 1.

Tasks are structured into **P0 Blockers** (mandatory pre-launch gates), **P1 Hardening** (operational resilience & observability), and **P2 Optimizations** (scale & hardware protection).

---

## 1. Roadmap Master Execution Matrix

| Priority | Identifier | Workstream Item | Target Component | Core Risk Addressed | Status |
|---|---|---|---|---|---|
| **P0** | `P0-1` | Credential & Secret Rotation | Auth / VPS / Pi / Firmware | Default `admin/admin123` vulnerability | Open |
| **P0** | `P0-2` | Production PostgreSQL 16 Cutover | Database / Server / Systemd | SQLite single-writer lock bottlenecks | **Completed** |
| **P0** | `P0-3` | ATS Physical Wiring & Node Reflash | Electrical / Firmware / Edge | 55V floating reading & reset race conditions | Open |
| **P0** | `P0-4` | Perimeter Firewall & Fail2ban | VPS Host / Nginx / SSH | Exposed ports and brute-force attacks | Open |
| **P1** | `P1-1` | Structured JSON Logging Pipeline | Server Core / Middleware | Invisible unstructured logs & lost traces | **Completed** |
| **P1** | `P1-2` | External Critical Alert Dispatcher | Alert Engine / Background Task | Zero notifications during power outages | Open |
| **P1** | `P1-3` | Zero-Downtime Push Deploy & Pre-Flight Gating | Deploy Pipeline / Git Hook | 502 Bad Gateway downtime & broken builds | **Completed** |
| **P1** | `P1-4` | Automated VPS Disaster Recovery Cron | Ops Tooling / Storage | Unbacked database on VPS | Open |
| **P1** | `P1-5` | Telemetry Cadence, RBE Deadband & UI Harmonization | Edge / Server / Firmware / UI | SD card churn, presence flapping, false chart outage hatches | **Completed** |
| **P2** | `P2-1` | Prometheus Metrics & Grafana APM | Server / Monitoring / Node Exporter | Blindness to latencies, RPS, and memory | Open |
| **P2** | `P2-2` | Hardware Watchdog & OverlayFS | Edge Hardware / OS / Storage | SD card corruption & kernel freezes | Open |
| **P2** | `P2-3` | Public Let's Encrypt TLS & HSTS | Nginx / Ingress / DNS | Self-signed browser security warnings | Open |
| **P2** | `P2-4` | Over-The-Air (OTA) Firmware Updates | Firmware / Wi-Fi Network | Need for physical FTDI flashing on-site | Open |

---

## 2. P0 Blockers: Immediate Pre-Launch Requirements

These items must be completed before any operational handover or production data ingestion.

### Task P0-1: Mandatory Credential & Secret Rotation
- **Context & Risk**: The production VPS currently operates with weak default credentials (`admin/admin123`) and a staging `HUB_KEY`.
- **Action Plan**:
  1. Execute `tools/rotate_credentials.py` against the production database:
     ```bash
     python tools/rotate_credentials.py --target-db postgresql://smsb:<PASSWORD>@127.0.0.1:5432/smsb_prod \
         --update-env /opt/smsb/server/.env --hub-id hs109rs-hub-01
     ```
  2. Invalidate all active user sessions (`DELETE FROM sessions`) and reset lockout counters.
  3. Synchronize `HUB_KEY` into edge `/home/hubadmin/smsb/hub/.env` and restart `hubbrain.service`.
  4. Rotate Mosquitto PBKDF2 password via `tools/generate_mosquitto_passwd.py` and synchronize firmware `secrets.h`.
- **Acceptance Criteria**:
  - `python tools/verify_prod_env.py --mode prod` passes with 0 failures and 0 warnings.
  - Logging in with `admin123` returns `HTTP 401 Unauthorized`.
  - Edge gateway successfully transmits batches authenticated by the new 64-character hex `HUB_KEY`.

### Task P0-2: Production Database Cutover to Dedicated PostgreSQL 16 [COMPLETED]
- **Status**: **Completed (2026-09-12)**
- **Context & Resolution**: SQLite WAL mode previously enforced single-writer serialization, making it prone to lock timeouts under multi-hub concurrency or simultaneous 30-day downsampling queries. On 2026-09-12, the live production VPS (`100.108.98.30`) was cut over to PostgreSQL 16 (`smsb_prod`).
- **Cutover Verification & Parity**:
  - **4,152,334 rows** migrated across all 14 canonical tables with **100% row parity** via `tools/migrate_sqlite_to_postgres.py`.
  - Memory-bounded streaming (`fetchmany(25000)` into `psycopg2.copy_expert()`) completed under a peak footprint of < 45MB RAM.
  - Secondary B-Tree and BRIN indexes were deferred during ingestion and reconstructed across partition hierarchies via sequential heap scans.
  - Monthly declarative range partitioning (`RANGE (timestamp)`) and BRIN indexing (`pages_per_range=32, autosummarize=True`) active on telemetry tables (`data_table`, `temperature_data`, `ats_data`).
  - Active VPS configuration: 8 GB Dynamic RAM / 4 vCPUs host with SMSB running on a 4 GB allocation profile (reserving 4 GB for CTFd co-tenancy); Uvicorn bounded by `MemoryHigh=1.2G`, `MemoryMax=1.8G`.
- **Delivered Infrastructure**:
  1. **Engine Pool Hardening**: `server/databasev5.py` configured with hardened production connection pooling (`pool_size=20, max_overflow=10, pool_timeout=10, pool_recycle=1800, pool_pre_ping=True`) and 15s statement timeout guard.
  2. **Streaming Migration Engine (`tools/migrate_sqlite_to_postgres.py`)**: High-throughput streaming tool with UTC normalization, integer-to-bool casting, JSONB formatting, replica role bypass, sequence sync, and parity verification.
  3. **Operational Cutover Runbook (`docs/runbooks/postgres_cutover_runbook.md`)**: Complete step-by-step procedure codified and executed with verified zero data loss.
- **Verified Acceptance**:
  - `curl -k https://127.0.0.1/api/health` returns `{"status":"ok","db":"up"}` against PostgreSQL backend.
  - Concurrency benchmarks validate: 30d history downsample P95 < 300ms, batch throughput > 500 pts/sec, 0 database locked errors.

### Task P0-3: Field Electrical ATS Physical Wiring & Node Firmware Reflash
- **Context & Risk**: Genset sensing wires are disconnected (~55V floating state); field nodes run unproofed legacy code susceptible to RST re-latch lockups.
- **Action Plan**:
  1. Complete physical field wiring: Connect Generator L1, L2, L3, and Neutral leads to ATS voltage divider sensing inputs.
  2. Connect serial programmer to ATS Pro Mini and flash `firmware/PROMINI/PROMINI.ino`.
  3. Flash `firmware/WEMOS_ATS` to the ESP8266 Wi-Fi bridge node using esptool.
  4. Power cycle ATS control panel and observe hardware state transitions.
- **Acceptance Criteria**:
  - ATS telemetry published to `hs109rs/hs109rs-hub-01/ats/68:C6:3A:D7:60:47` reports true generator voltage (0V when stopped, ~220V/380V when running), eliminating the 55V floating state.
  - Reset switch does not latch or freeze the Pro Mini FSM.

### Task P0-4: Host Perimeter Firewall & Intrusion Prevention
- **Context & Risk**: Unfiltered host ports risk exposing internal databases; lack of brute-force detection leaves the authentication endpoint exposed.
- **Action Plan**:
  1. Configure UFW (Uncomplicated Firewall) on `genset` VPS:
     ```bash
     sudo ufw default deny incoming
     sudo ufw default allow outgoing
     sudo ufw allow 22/tcp comment 'SSH'
     sudo ufw allow 80/tcp comment 'Nginx HTTP'
     sudo ufw allow 443/tcp comment 'Nginx HTTPS'
     sudo ufw enable
     ```
  2. Enforce SSH key-only authentication on VPS and Pi:
     ```bash
     sudo bash -c 'echo "PasswordAuthentication no" > /etc/ssh/sshd_config.d/99-disable-passwords.conf'
     sudo systemctl restart ssh || sudo systemctl restart sshd
     ```
  3. Install Fail2ban:
     ```bash
     sudo apt install -y fail2ban
     ```
  4. Author `/etc/fail2ban/jail.d/smsb.conf` protecting SSH and Nginx `/api/auth/login` (ban IP for 1 hour after 5 failed attempts in 10 minutes).
- **Acceptance Criteria**:
  - Port scan against public IP verifies only ports 80 and 443 (and authorized SSH) accept connections. Direct connections to 5432, 8000, and 1883 are dropped.
  - SSH login attempting password authentication is rejected immediately (`Permission denied (publickey)`).
  - 5 rapid invalid logins to `/api/auth/login` trigger immediate IP jail in Fail2ban.

---

## 3. P1 Hardening: Operational Stability & Observability

These items establish system stability, fault detection, and deployment safety.

### Task P1-1: Structured JSON Logging Pipeline [COMPLETED]
- **Status**: **Completed**
- **Context & Risk**: Production logs previously emitted flat unstructured text, preventing automated log indexing and transaction tracking.
- **Resolution**:
  1. Implemented `StructuredLoggingMiddleware` in `server/app/core/logging.py` mounted in `server/app/main.py`.
  2. Leverages standard-library `json.dumps()` with a dedicated `smsb.access` logger, completely eliminating external dependencies on `python-json-logger`.
  3. Attaches `X-Request-ID` to response headers, calculates `latency_ms` via `time.perf_counter()`, resolves client IP via `get_forwarded_address()`, and exposes `X-Request-ID` in CORS headers.
  4. Emits single-line JSON records (`timestamp`, `request_id`, `method`, `path`, `status_code`, `latency_ms`, `client_ip`) parseable by log aggregators.

### Task P1-2: External Real-Time Alert Notification Dispatcher
- **Context & Risk**: Critical electrical failures (mains loss, generator failure, thermal runaway) are logged passively in the database with zero external alert dispatching.
- **Action Plan**:
  1. Create `server/app/services/alert_dispatcher.py` running as an async background task in FastAPI's lifespan.
  2. Implement an outbox processor that checks `event_log` for unnotified rows where `severity IN ('CRITICAL', 'WARNING')`.
  3. Integrate Telegram Bot API (`https://api.telegram.org/bot<TOKEN>/sendMessage`) with Markdown message formatting.
  4. Include rate limiting and deduplication (maximum 1 notification per device per 5 minutes for repeating alerts).
  5. Add configuration variables to `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ENABLE_EXTERNAL_ALERTS`.
- **Acceptance Criteria**:
  - Triggering a simulated emergency trip publishes a formatted Telegram notification to the operations channel within 3 seconds.
  - Rapid repeated trips are throttled to prevent notification flooding.

### Task P1-3: Zero-Downtime Push Deployment & Automated Rollback [COMPLETED]
- **Status**: **Completed**
- **Context & Risk**: `git push prod main` restarts Uvicorn abruptly, risking deployment of broken syntax or unimportable code that leaves the service down.
- **Resolution**:
  1. **Previous Revision Tracking**: `deploy/setup_push_deploy.sh` captures `oldrev` from the live work tree prior to pulling new commits.
  2. **Pre-Flight Syntax Compilation Gate**: Runs `python -m compileall -q /opt/smsb/server`. If any file contains syntax errors, the post-receive hook immediately reverts the work tree (`git reset --hard "${oldrev}"`) and exits without restarting or disrupting the running service.
  3. **Pre-Flight Application Import Gate**: Runs `python -c "from app.main import api"`. If application assembly fails due to broken imports, circular dependencies, or schema misconfigurations, the hook immediately reverts the work tree (`git reset --hard "${oldrev}"`) and aborts deployment.
  4. **SPA Build Gate**: Gated `dashboard` build to only sync assets to `/var/www/gui-app` when `npm run build` succeeds with exit 0.
- **Acceptance Criteria Met**:
  - Pushing syntax or import regressions automatically triggers a work-tree rollback to `${oldrev}` with zero service downtime.
  - Service restart occurs only after both Python syntax and application import validation pass completely.

### Task P1-4: Automated VPS Disaster Recovery Backup Cron
- **Context & Risk**: VPS database state lacks automated off-site backups, risking total data loss if the VPS host fails.
- **Action Plan**:
  1. Author `/opt/smsb/tools/backup_vps.sh`:
     - Executes `pg_dump -Fc smsb_prod` to create compressed binary snapshot.
     - Saves archive with timestamp to `/opt/backups/smsb/`.
     - Validates archive integrity and generates SHA256 checksum file.
     - Enforces local retention policy (prunes backups older than 30 days).
  2. Install root cron job:
     ```cron
     0 2 * * * /opt/smsb/tools/backup_vps.sh >> /var/log/smsb_backup.log 2>&1
     ```
  3. Configure encrypted offload to remote S3-compatible bucket or secondary backup server via `rclone`.
- **Acceptance Criteria**:
  - Nightly cron produces verified `.dump` and `.sha256` files.
  - Disaster recovery restoration test successfully restores a database dump into a test instance in under 5 minutes.

### Task P1-5: Telemetry Cadence, RBE Deadband & UI Harmonization [COMPLETED]
- **Status**: **Completed (2026-09-17)**
- **Context & Risk**:
  - High-frequency telemetry (5s TS, 2s ATS) saturated 2.4 GHz Wi-Fi airtime, caused SQLite WAL churn on edge SD cards, and risked presence flapping false alarms.
  - Transitioning nodes to relaxed Report-by-Exception (RBE) cadences (TS: 5m steady, AC: 2m steady, ATS: 1m steady) caused static chart gap thresholds (2-5m) to erroneously render dark outage hatches across healthy historical telemetry.
- **Resolution & Architecture**:
  1. **Phase 1: Edge Hub Deadband & Change-of-Value Filter (`hub/main.py`)**:
     - Evaluates incoming telemetry against delta thresholds (TS: $\pm 0.5^\circ\text{C}$, $\pm 2.0\%\text{RH}$; ATS: $\pm 3.0\text{V}$; AC: $\pm 1.0^\circ\text{C}$).
     - Bypasses filter instantly (<100ms) on discrete state transitions and triggers a 2.0s dynamic burst for 60s during electrical events.
  2. **Phase 2: Central Backend Presence Engine Alignment (`server/app/services/presence.py`)**:
     - Type-aware presence windows: ATS 180s (3m), AC 360s (6m), TS 900s (15m).
     - Composite indexes on `dev_table` (`ix_dev_table_active_last_seen`, `ix_dev_table_dev_type`).
  3. **Phase 3: Firmware Fleet Optimization (`firmware/`)**:
     - ESP8266 nodes decoupled: 1 Hz local sensor oversampling and OLED refresh; steady publish interval set to 5m (TS), 2m (AC), 60s (ATS).
  4. **Phase 4: Dashboard UI Harmonization & Chart Gap Alignment (`dashboard/`)**:
     - Added `GAP_FLOOR_BY_TYPE_MIN` (`{ TS: 15, AC: 6, ACC: 6, ATS: 3, DEFAULT: 3 }` minutes) and `CADENCE_BY_TYPE` nominal cadence metadata in `src/lib/constants.ts`.
     - Implemented pure functional `getGapThresholdMinutes(devType, rangeMinutes)` and updated `getGapThresholdMs` in `src/lib/chartUtils.ts` to prevent false outage hatches during normal RBE cadences and dynamically scale for extended historical windows (24h: 24m, 7d: 168m, 30d: 720m).
     - Added subtle reporting cadence badge ("Cadence: 5m RBE", "1m RBE", "2m RBE") in device detail header (`src/routes/device.$deviceId.tsx`).
     - Added comprehensive vitest suite in `src/lib/chartUtils.test.ts` (100% passing).

---


## 4. P2 Optimizations: Scale, Resilience & Hardware Hardening

These items ensure long-term sustainability, scale, and edge reliability.

### Task P2-1: Prometheus Metrics Exposition & Grafana APM
- **Context & Risk**: System health is opaque; latency degradation or memory leaks cannot be diagnosed proactively.
- **Action Plan**:
  1. Add `prometheus-fastapi-instrumentator` to `server/requirements.txt`.
  2. Mount `/metrics` endpoint on FastAPI, secured via basic auth or internal network restriction.
  3. Instrument custom metrics:
     - `smsb_telemetry_ingest_points_total` (counter, labels: `hub_id`, `dev_type`).
     - `smsb_telemetry_batch_size` (histogram).
     - `smsb_downsampling_query_duration_seconds` (histogram, labels: `range`).
     - `smsb_db_pool_active_connections` (gauge).
  4. Deploy `prometheus` and `grafana` via `docker-compose.yml` on monitoring host.
- **Acceptance Criteria**:
  - Prometheus scrapes `/metrics` every 15s with response latency < 20ms.
  - Grafana dashboard visualizes real-time RPS, P95 downsampling latency, and active connection pool status.

### Task P2-2: Edge Hardware Watchdog & Read-Only OverlayFS
- **Context & Risk**: SD card corruption from continuous SQLite writes and unrecoverable kernel freezes during power anomalies.
- **Action Plan**:
  1. Enable hardware watchdog in `/etc/systemd/system.conf`:
     ```ini
     RuntimeWatchdogSec=15s
     RebootWatchdogSec=30s
     ```
  2. Configure systemd to ping `/dev/watchdog`.
  3. Convert Raspberry Pi OS root filesystem to Read-Only OverlayFS using `raspi-config nonint enable_overlayfs`.
  4. Mount `/home/hubadmin/smsb/hub/data` on a dedicated wear-levelled partition or zram tmpfs for `edge_cache.db`.
- **Acceptance Criteria**:
  - Kernel panic or fork-bomb test triggers automated hardware reboot within 30 seconds.
  - Abrupt power removal during heavy simulated MQTT ingestion produces zero filesystem corruption errors on reboot.

### Task P2-3: Trusted Public TLS Certificates & HSTS Activation
- **Context & Risk**: Self-signed certificates trigger browser security warnings and preclude HSTS enforcement.
- **Action Plan**:
  1. Assign a public FQDN (e.g. `smsb.facility.example.com`) to VPS public IP.
  2. Install Certbot and configure automated Let's Encrypt certificate generation:
     ```bash
     sudo apt install -y certbot python3-certbot-nginx
     sudo certbot --nginx -d smsb.facility.example.com
     ```
  3. Update `deploy/nginx_smsb.conf` to enable the HSTS header:
     ```nginx
     add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
     ```
- **Acceptance Criteria**:
  - Accessing dashboard via web browser displays valid trusted lock icon without certificate warnings.
  - Qualys SSL Labs scan achieves an `A+` grade.

### Task P2-4: Wireless Over-The-Air (OTA) Firmware Updates
- **Context & Risk**: Updating ESP8266 sensor nodes requires physical serial cable connections, making field updates labor-intensive.
- **Action Plan**:
  1. Implement `ArduinoOTA` in `firmware/WEMOS_ATS`, `firmware/WEMOS_TS`, and `firmware/WEMOS_AC`.
  2. Secure OTA endpoints with MD5/SHA256 authentication passwords stored in `secrets.h`.
  3. Author deployment script `tools/deploy_firmware_ota.py` that discovers nodes on `smsb-iot` Wi-Fi and updates binaries over HTTP.
- **Acceptance Criteria**:
  - ESP8266 nodes can receive and reboot into new firmware binaries remotely over the local Wi-Fi network.
