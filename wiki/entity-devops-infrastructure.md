---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-deploy-pipeline.md, wiki/entity-hubgate-v5.md, wiki/entity-hubbrain-v5.md, wiki/concept-observability-monitoring.md, wiki/concept-production-readiness.md, wiki/workstream-production-grade-roadmap.md]
sources: [deploy/nginx_smsb.conf, deploy/smsb-api.service, deploy/hubbrain.service, deploy/setup_push_deploy.sh, deploy/journald.conf.dropin, tools/backup_hub.sh, tools/run_pi_backup.py, tools/rotate_credentials.py, tools/migrate_sqlite_to_postgres.py, docs/runbooks/postgres_cutover_runbook.md, notes/field-ops.md]
updated: 2026-09-04
---

# DevOps & Infrastructure Architecture

The SMSB deployment and operational infrastructure governs the host topology, reverse proxy routing, service virtualization, automated push deployment, and disaster recovery mechanisms spanning the central cloud server and on-premise edge hardware.

---

## 1. Host Topology & System Architecture

The physical and virtual topology is organized into three segregated tiers:

```
+-------------------------------------------------------------------------+
| CENTRAL VPS TIER (Host: genset, Tailscale IP: 100.108.98.30)           |
|                                                                         |
|  [Clients / Browser SPA] ----> Nginx Ingress (:80 -> :443 TLS)          |
|                                      |                                  |
|         +----------------------------+-----------------------------+    |
|         | / (Static SPA)             | /api/ (Reverse Proxy)       |    |
|         v                            v                             |    |
|   /var/www/gui-app            smsb-api.service (Uvicorn / FastAPI) |    |
|   (Vite React 19 SPA)         User: smsb (127.0.0.1:8000)          |    |
|                                      |                             |    |
|                                      v                             |    |
|                         PostgreSQL 16 / SQLite WAL                  |    |
+-------------------------------------------------------------------------+
                                       ^
                                       | HTTPS Ingestion / Replay
                                       | (X-Hub-ID / X-Hub-Key)
+-------------------------------------------------------------------------+
| EDGE GATEWAY TIER (Raspberry Pi, eth0: 10.33.102.10, AP: 192.168.72.242)|
|                                                                         |
|  hubbrain.service (User: hubadmin, MemoryMax=150M)                      |
|    - Local Mosquitto MQTT Broker (:1883, auth via passwd PBKDF2)        |
|    - HubBrain V5 Ingestion & Offline Buffer (SQLite edge_cache.db)      |
|    - Local NTP Sync Target: 10.33.102.172                               |
+-------------------------------------------------------------------------+
                                       ^
                                       | MQTT (hs109rs/#)
                                       | Wi-Fi SSID: smsb-iot
+-------------------------------------------------------------------------+
| SENSOR & ACTUATOR NODES (ESP8266 D1 Mini / ATmega328P Pro Mini)        |
|                                                                         |
|  - WEMOS_ATS: Canonical ATS electrical bridge (Generator/Mains Sensing) |
|  - WEMOS_TS: Ambient Temperature & Humidity (SHT30)                     |
|  - WEMOS_AC: Infrared Air Conditioner Automation                        |
+-------------------------------------------------------------------------+
```

### Central Server Specifications (`genset`)
- **Network Identity**: Tailscale interface `100.108.98.30`, public ingress via Nginx on ports 80 and 443.
- **System Constraints**: 1 GB total RAM budget. Memory consumption is strictly bounded per process via systemd cgroups.
- **User Segregation**:
  - `genset`: Unprivileged deployment user. Possesses SSH key access and narrow sudoers permission to restart `smsb-api`.
  - `smsb`: Dedicated system execution user (`no-login`). Runs the FastAPI/Uvicorn process and owns the server `.env` and SQLite database files.
- **Perimeter & Access Control Posture**:
  - **Firewall**: UFW/nftables is not currently active on the host. Perimeter containment relies solely on loopback socket binding (`127.0.0.1:8000` for Uvicorn, `127.0.0.1:5432` for PostgreSQL) and Nginx reverse proxy mediation.
  - **SSH Enforcement**: Authorized operator workstations connect via SSH key authentication, but password authentication remains permitted in `/etc/ssh/sshd_config` (`PasswordAuthentication yes`). Fail2ban is uninstalled, leaving port 22 exposed to brute-force dictionary attacks.

### Edge Gateway Specifications (`hubadmin`)
- **Hardware**: Raspberry Pi running Raspberry Pi OS (Linux).
- **Network Configuration**:
  - `eth0`: Campus LAN uplink at `10.33.102.10` (staging address `10.33.36.81`).
  - `wlan0`: Isolated Software Access Point (`hostapd` + `dnsmasq`) on `192.168.72.242`, SSID `smsb-iot`.
  - `NTP`: Time synchronization synchronized against local server `10.33.102.172`.

---

## 2. Nginx Reverse Proxy & Same-Origin TLS Routing

The central ingress is managed by Nginx (`deploy/nginx_smsb.conf`), implementing a strict same-origin architecture. The FastAPI backend is never exposed to public network interfaces.

### Port 80: HTTP Redirect
Port 80 enforces permanent HTTP-to-HTTPS upgrade:
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}
```

### Port 443: TLS Termination & Security Settings
- **Protocols & Ciphers**: Restricts negotiation to `TLSv1.2` and `TLSv1.3`. Ciphers enforced: `HIGH:!aNULL:!MD5:!3DES`.
- **Certificates**: Self-signed certificate stored at `/etc/nginx/ssl/smsb.crt` and `/etc/nginx/ssl/smsb.key`, generated with Subject Alternative Names (SANs) covering the public IP, Tailscale IP `100.108.98.30`, and `genset`.
- **HSTS Policy**: `Strict-Transport-Security` is intentionally disabled while using self-signed certificates. Hard-pinning an untrusted certificate chain risks locking client browsers permanently upon certificate re-generation.
- **Security Headers**:
  - `X-Content-Type-Options "nosniff" always;`
  - `X-Frame-Options "DENY" always;`
  - `X-XSS-Protection "1; mode=block" always;`
  - `Referrer-Policy "strict-origin-when-cross-origin" always;`
  - `Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;`
- **Compression**: Gzip level 5 enabled for text payloads (`application/json`, `text/css`, `application/javascript`, `text/javascript`, `image/svg+xml`) with `gzip_min_length 256` and `gzip_vary on`.

### Ingress Route Table
| Location Path | Target Destination | Caching & Buffering Policy |
|---|---|---|
| `/` | `/var/www/gui-app` (SPA Build) | `try_files $uri $uri/ /index.html`. Dedicated block for `= /index.html` enforces `no-cache, no-store, must-revalidate` with `expires 0`. |
| `/assets/` | `/var/www/gui-app/assets/` | Immutable Vite hashed bundles. `expires 1y`, `Cache-Control "public, immutable"`, `access_log off`. |
| `/static/` | `/opt/smsb/server/static/` | Aliased upload path (floor plans). `expires 30d`. Fallback via `try_files $uri @api_backend` proxies missing files to FastAPI. |
| `/api/` | `http://127.0.0.1:8000` | Reverse proxy to FastAPI / Uvicorn. HTTP/1.1 with WebSocket support (`Upgrade $http_upgrade`, `Connection "upgrade"`). `proxy_buffering on`, 60s read/send timeouts. |

---

## 3. Systemd Service Management & Sandboxing

All persistent services are managed by systemd with explicit memory caps, auto-recovery policies, and filesystem sandbox isolation.

### Central Gateway Unit (`deploy/smsb-api.service`)
Installed at `/etc/systemd/system/smsb-api.service`:
- **Identity & Directories**:
  - `User=smsb`, `Group=smsb`
  - `WorkingDirectory=/opt/smsb/server`
  - `EnvironmentFile=/opt/smsb/server/.env`
- **Execution Command**:
  ```ini
  ExecStart=/opt/smsb/venv/bin/python -m uvicorn app.main:api \
      --host 127.0.0.1 --port 8000 --workers 1 --limit-concurrency 50 \
      --proxy-headers --forwarded-allow-ips=127.0.0.1
  ```
- **Lifecycle & Resource Ceiling**:
  - `Restart=always`, `RestartSec=5`
  - `MemoryHigh=650M`, `MemoryMax=800M`: Hard kernel cgroup ceiling. A memory leak or runaway worker will be terminated by systemd before depleting the 1 GB host RAM.
- **Security Sandboxing Directives**:
  - `NoNewPrivileges=yes`: Disallows setuid/sudo privilege escalation.
  - `ProtectSystem=strict`: Entire filesystem is mounted read-only for the process.
  - `ProtectHome=yes`: Denies access to `/home`, `/root`, and `/run/user`.
  - `PrivateTmp=yes`: Dedicated, isolated `/tmp` namespace.
  - `RestrictSUIDSGID=yes`: Blocks creation of setuid/setgid binaries.
  - `ProtectKernelTunables=yes`, `ProtectControlGroups=yes`: Blocks sysctl and cgroup tampering.
  - `ReadWritePaths=/opt/smsb/server`: Single write exception allowing SQLite writes, log creation, and image uploads.

### Edge Gateway Unit (`deploy/hubbrain.service`)
Installed on the Raspberry Pi at `/etc/systemd/system/hubbrain.service`:
- **Identity**: `User=hubadmin`, `Group=hubadmin`.
- **Working Directory**: `/home/hubadmin/smsb/hub`.
- **Environment**: Secrets loaded exclusively from `/home/hubadmin/smsb/hub/.env`.
- **Dependencies**: `After=network-online.target mosquitto.service`.
- **Resource Ceiling**: `MemoryMax=150M`, `Restart=always`, `RestartSec=10` (cooldown avoids thrashing CPU during upstream WAN outages).
- **Sandboxing**: `ProtectSystem=strict`, `PrivateTmp=yes`, `ReadWritePaths=/home/hubadmin/smsb/hub` (permits local write-ahead log updates in `edge_cache.db`).

### Journal Disk Quota (`deploy/journald.conf.dropin`)
To prevent journald from exhausting root disk space on the 1 GB VPS, a drop-in configuration `/etc/systemd/journald.conf.d/99-smsb-size.conf` enforces:
```ini
[Journal]
SystemMaxUse=100M
```

---

## 4. Git Push-to-Deploy Architecture

Deployments to production execute via standard Git transport over SSH (`deploy/setup_push_deploy.sh`).

### Infrastructure Components
1. **Bare Repository**: Located at `/opt/smsb.git`, owned by `genset:genset`.
2. **Work Tree Clone**: Located at `/opt/smsb`, owned by `genset:smsb` with group write and setgid permissions (`chmod -R g+rwX`, `chmod g+s`).
3. **Sudoers Rule**: `/etc/sudoers.d/smsb-deploy` grants passwordless service restart:
   ```sudoers
   genset ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart smsb-api.service
   ```

### Execution Pipeline (`post-receive` Hook)
When a developer runs `git push prod main`:
1. **Branch Gate**: Non-main refs are ignored.
2. **Work Tree Sync & Old Revision Capture**: Captures the current HEAD revision (`oldrev=$(cd "${DEPLOY_WORK_TREE}" && git rev-parse HEAD)`), clears Git environment variables, and executes `git fetch origin main && git reset --hard origin/main` in `/opt/smsb`.
3. **Python Dependency Sync**: Executes `/opt/smsb/venv/bin/pip install --quiet -r server/requirements.txt`.
4. **Pre-Flight Syntax & Import Gating**:
   - Compiles all Python source files via `python -m compileall -q "${DEPLOY_WORK_TREE}/server"`. On syntax compilation error, the hook immediately reverts the work tree via `git reset --hard "${oldrev}"` and aborts without touching the running service.
   - Verifies canonical application import via `python -c "from app.main import api"`. On import failure, the hook immediately reverts the work tree via `git reset --hard "${oldrev}"` and aborts without touching the running service.
5. **Gated SPA Compilation**: Invokes NVM Node 22 (`npm ci --ignore-engines && npm run build --ignore-engines`) in `/opt/smsb/dashboard`. Only syncs assets to `/var/www/gui-app/` if the build exits with 0.
6. **Daemon Restart**: Invokes `sudo -n systemctl restart smsb-api.service`.
7. **Post-Deploy Smoke Verification**:
   - Polling check: `https://127.0.0.1/api/auth/me` must return `HTTP 401 Unauthorized`.
   - SPA check: `https://127.0.0.1/` must return HTML containing `<title>`.
   - Unit check: `systemctl is-active --quiet smsb-api` must return 0.
8. **Failure Handling**: If any post-restart smoke check fails, the hook prints actionable manual rollback instructions.

---

## 5. Backup, Disaster Recovery & Concurrency Harness

### Edge Gateway Backup Gate (`tools/backup_hub.sh`)
Mandatory gate required prior to edge hardware updates or kernel modifications:
- **Scope**: Archives `/etc/NetworkManager/system-connections`, `/etc/hostapd/hostapd.conf`, `/etc/dnsmasq.conf`, `/etc/dnsmasq.d`, `/etc/mosquitto`, `/etc/systemd/system/hubbrain*.service`, `hub/.env`, `hub/cert.crt`, and `hub/edge_cache.db`.
- **Integrity Assertion**: Builds a compressed tarball (`hubbrain_backup_<timestamp>.tar.gz`), validates internal structure via `tar -tzf`, and calculates SHA256 checksums.
- **Remote Automation (`tools/run_pi_backup.py`)**: Uses Paramiko to stage the backup script over SFTP, execute it with root privileges, download the archive and checksum off-device, and verify SHA256 integrity locally.

### Central Server Disaster Recovery & Migration Pipeline
- **SQLite-to-PostgreSQL 16 Streaming Migration (`tools/migrate_sqlite_to_postgres.py`)**: Dedicated low-memory streaming ETL tool migrating historical telemetry, configuration, and relational entities from SQLite 3 WAL to PostgreSQL 16. Validated via `--dry-run` and live parity check reporting.
- **PostgreSQL Cutover Runbook (`docs/runbooks/postgres_cutover_runbook.md`)**: Comprehensive operational runbook detailing pre-flight checks, T-0 WAL truncation (`PRAGMA wal_checkpoint(TRUNCATE)`), read-only service freeze, streaming migration execution, and verification under a $\le 3\text{ minute}$ maintenance window.
- **Automated Backup Posture**: Nightly cron executing `pg_dump` with SHA256 verification and off-site cloud storage replication (`tools/backup_vps.sh`).

### Production Credential Rotation Harness (`tools/rotate_credentials.py`)
Provides automated, atomic rotation of system secrets:
- Rotates web user passwords (`admin`, `operator`, `viewer`) using Argon2id password hashing.
- Generates 64-character hexadecimal `HUB_KEY` tokens.
- Updates database user records and `hub_table` in SQLite or PostgreSQL.
- Flushes active web user sessions (`DELETE FROM sessions`) and resets failed login counters.
- Updates `HUB_KEY` in `server/.env` while preserving file comments.
- Emits operational runbooks for edge gateway, Mosquitto broker, and ESP8266 node synchronization.

### Concurrency Stress Benchmark Harness (`tools/benchmark_concurrency_stress.py`)
Async multi-worker benchmarking harness simulating production concurrency:
- **Workloads**: High-throughput ingestion writes (`POST /api/iot/batch`), analytical downsampling reads (`GET /api/devices/{id}/history?range=30d`), and live dashboard polling reads (`GET /api/devices`, `GET /api/rooms`, `GET /api/alerts`).
- **Engine Discrimination**: Differentiates between SQLite 3 (WAL mode) and PostgreSQL 16.
- **Verified SLAs**:
  - Downsampling P95 latency < 1000ms (SQLite) / < 300ms (PostgreSQL).
  - Batch ingestion write P95 latency < 350ms, P99 < 750ms.
  - Ingestion throughput > 500 points/second.
  - Zero database lock errors (`database is locked == 0`), zero timeouts, and zero HTTP 500 errors.
