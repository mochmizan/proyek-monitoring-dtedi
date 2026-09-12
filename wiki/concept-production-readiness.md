---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-devops-infrastructure.md, wiki/concept-observability-monitoring.md, wiki/entity-deploy-pipeline.md, wiki/workstream-production-grade-roadmap.md]
sources: [deploy/, tools/, server/, hub/, firmware/, git:notes/field-ops.md (archived), git:notes/benchmarks-baseline.md (archived)]
updated: 2026-09-12
---

# Production Readiness Gap Assessment

A holistic evaluation of the SMSB platform across five operational pillars: Backend/Server, Frontend/Dashboard SPA, Edge Gateway, Firmware & Electrical, and DevOps/Infrastructure Security.

---

## 1. Readiness Evaluation Matrix

| Domain | Hardened Capabilities (Current State) | Production Gaps & Vulnerabilities | Maturity Level |
|---|---|---|---|
| **Backend & Database** | Single-transaction atomic commit (CRIT-01); in-memory throttled `HubAuthCache`; idempotent WAL replay with `uuid5` PKs; Downsampling V2 window functions; Argon2id auth with lockout; active PostgreSQL 16 MVCC (`smsb_prod`, 4.15M rows, 100% parity) with monthly range partitioning and BRIN indexes; automated Alembic pre-deploy migration gating. | External connection pool telemetry & Prometheus metrics exporter pending (P2-1); automated nightly pg_dump offsite replication pending (P1-4). | **Production-Grade** |
| **Frontend SPA** | React 19 / Vite build; TanStack Query 4-tier jittered polling (1.5s/6s/15s/60s) with `keepPreviousData` (zero layout shift); dynamic chart envelopes; same-origin reverse proxying; bounded Node build heap cap (1024MB) + 2GB swap. | No client-side error telemetry (Sentry); no Service Worker offline cache. | **Hardened Staging** |
| **Edge Gateway (Pi)** | Mosquitto broker isolation; bounded 20,000-row SQLite WAL queue; capture epoch preservation (`_hub_created_at`); mandatory backup script. | High SD card corruption risk from continuous SQLite WAL writes without OverlayFS; hardware watchdog inactive; plaintext `.env` secrets on edge disk. | **Staging Prototype** |
| **Firmware & Electrical** | Unified WEMOS_ATS canonical bridge; non-blocking millis loops; Pro Mini RST re-latch race condition resolved in code. | Genset voltage leads physically NOT wired to ATS (~55V floating); proofed firmware pending physical flashing to field nodes; no OTA update mechanism. | **Lab Verified** (Field Blocked) |
| **DevOps & Security** | Sandboxed systemd units; Nginx same-origin reverse proxy; git push-to-deploy; automated credential rotation CLI (`tools/rotate_credentials.py`). | Weak default credentials (`admin/admin123`) live on VPS; self-signed TLS certs; no VPS firewall (UFW) or Fail2ban; deploy restarts cause 2-5s downtime; zero active alert dispatch. | **Staging Prototype** |

---

## 2. Server & Database Tier Gaps

### 1. PostgreSQL 16 Multi-Writer Production Cutover [RESOLVED]
The SQLite single-writer lock contention risk was permanently resolved on 2026-09-12 via the completed cutover to PostgreSQL 16:
- **Production Host**: Dedicated VPS (`100.108.98.30`) running `smsb_prod` on PostgreSQL 16 under an 8 GB Dynamic RAM / 4 vCPUs configuration (4 GB allocation profile for SMSB, reserving 4 GB for CTFd co-tenancy).
- **Migration Parity**: 4,152,334 rows were migrated from SQLite with 100% parity across all 14 canonical tables using `tools/migrate_sqlite_to_postgres.py` (< 45MB RAM footprint).
- **Declarative Partitioning & BRIN**: Telemetry tables employ monthly range partitioning and compact BRIN indexes, enabling logarithmic history scans and O(1) concurrent retention detachment without locking writers.
- **Role of SQLite**: SQLite 3 WAL mode is retained strictly as the local development engine and Raspberry Pi edge offline queue (`edge_cache.db`).

### 2. Pre-Deployment Migration Safety Gates [RESOLVED]
The Git push-deploy pipeline (`deploy/setup_push_deploy.sh`) now enforces automated pre-flight database migrations:
- The `post-receive` hook executes `python -m alembic upgrade head` prior to restarting the service.
- If migration fails, the hook automatically executes `git reset --hard "${oldrev}"` and aborts deployment, leaving the running service intact and preventing schema drift.

---

## 3. Frontend / Dashboard SPA Tier Gaps

### 1. Resource Contention During In-Band VPS Build
- In `deploy/setup_push_deploy.sh`, the Git `post-receive` hook executes:
  ```bash
  ( cd "${SPA_DIR}" && npm ci --ignore-engines && npm run build --ignore-engines )
  ```
- Node 22 memory footprint during Vite compilation is capped via `NODE_OPTIONS="--max-old-space-size=1024"`.
- The bootstrap script provisions and enables a 2 GB `/swapfile` if active swap is under 1 GB, protecting the host and co-tenanted CTFd from OOM exhaustion during Vite compilation.

### 2. Client-Side Telemetry & Field Resilience
- **Zero Frontend Error Reporting**: JavaScript runtime errors, failed chunk downloads, or TanStack query fetch failures are invisible to operators and developers.
- **No Offline Service Worker**: Facility managers inspecting basement switchgear rooms often experience cellular dead zones. The SPA lacks offline asset caching or PWA manifest support to maintain UI accessibility during local signal loss.

---

## 4. Edge Gateway (Raspberry Pi) Tier Gaps

### 1. SD Card Wear & Power Loss Vulnerability
- HubBrain operates a local SQLite database (`edge_cache.db`) for write-ahead logging. Under normal continuous operation and frequent flush cycles, flash memory sectors on the micro-SD card undergo high write cycles.
- Sudden campus power outages while SQLite or the ext4 journal is flushing dirty pages risk corrupting the micro-SD card filesystem, requiring physical replacement or manual `fsck`.
- **Target**: Deploy Read-Only OverlayFS for the root filesystem, mounting `edge_cache.db` on a wear-levelled partition or RAM-backed tmpfs with periodic flush.

### 2. Missing Hardware Watchdog Protection
- The Broadcom BCM2835 hardware watchdog timer on the Raspberry Pi (`/dev/watchdog`) is not enabled in systemd.
- If kernel deadlocks, Wi-Fi driver hangs, or severe memory exhaustion freeze the board, HubBrain becomes permanently unresponsive until someone physically power-cycles the edge gateway.

---

## 5. Firmware & Electrical Subsystem Gaps

### 1. Physical Wiring Disconnect (Critical Operational Blocker)
- As recorded in historical field operations logs (archived in git history):
  > "Genset physically NOT wired to the ATS as of 31/8 (reads ~55V floating)."
- The generator voltage sensing lines have not been physically terminated to the voltage divider circuits on the ATS controller.
- The ATS logic currently reads approximately 55V of induced floating voltage instead of true zero or true 220V/380V generator phase voltage. This prevents the firmware from detecting generator startup or validating phase synchronization.

### 2. Physical Node Reflashing Pending
- Firmware fixes that eliminate the Pro Mini reset re-latch race condition (`firmware/WEMOS_ATS` and `firmware/PROMINI`) have been validated in the lab but have **not yet been flashed to the hardware in the field**.
- The physical hardware is still executing legacy firmware.
- The nodes do not support Over-The-Air (OTA) updates; deployment requires physical on-site access with FTDI serial programmers and avrdude/esptool.

---

## 6. DevOps, Security & Infrastructure Gaps

### 1. Default Credentials Live in Production
- According to historical deployment records (archived in git history), the production VPS continues to run with default credentials:
  ```
  admin / admin123
  ```
- This is a critical security vulnerability. Anyone discovering the host IP can authenticate to the API, modify room layouts, delete edge hubs, or issue remote actuator control commands.

### 2. Service Downtime During Git Push Deployment
- The `post-receive` deployment hook executes:
  ```bash
  sudo -n systemctl restart smsb-api.service
  ```
- A systemd restart shuts down existing Uvicorn worker processes, clears memory, and launches a fresh Python process.
- Cold startup on the VPS requires **2 to 5 seconds**, during which incoming HTTP requests from edge gateways or web clients receive `HTTP 502 Bad Gateway`.
- The pipeline lacks zero-downtime reload (such as Uvicorn process reload or dual-process blue/green socket handoff).

### 3. Non-Automated Advisory Rollback
- If post-deployment smoke checks fail in `setup_push_deploy.sh`, the script prints a textual "Rollback hint" and exits with status 1.
- It does **not automatically roll back the work tree clone** (`git reset --hard origin/main~1`) or re-launch the previous known-good service state. The broken deployment remains live and serving errors until a human manually intervenes.

### 4. Perimeter Exposure & Intrusion Defense Deficit
- **No Active Firewall**: UFW or nftables is not configured on the VPS. If internal services (PostgreSQL `:5432` or Mosquitto `:1883`) accidentally bind to `0.0.0.0`, they are exposed directly to the internet.
- **No Fail2ban**: The VPS lacks Fail2ban monitoring for SSH connection attempts and Nginx `/api/auth/login` brute-force sweeps.
- **Untrusted TLS Certificates**: Nginx terminates TLS using a self-signed certificate, triggering browser certificate warnings and preventing the deployment of HTTP Strict Transport Security (HSTS).

### 5. Secrets Management: Dev vs Production Divergence
- **Development Fallbacks**: Local development relies on permissive flags (`ALLOW_INSECURE_DEV_KEYS=true`), hardcoded mock tokens, and plain SQLite databases.
- **Production Plaintext Storage**: Production secrets (`DATABASE_URL`, `JWT_SECRET`, `HUB_KEY`, `MQTT_PASS`) are stored in unencrypted `.env` files directly on the host filesystems (mode 600, owned by `smsb` or `hubadmin`). No external secrets manager (HashiCorp Vault, AWS Secrets Manager, or age-encrypted sops) is integrated.
- **Firmware Secret Embedding**: Microcontroller nodes compile `MQTT_PASS` directly into C++ header files (`secrets.h`). Without cryptographic secure elements (e.g. ATECC608A) or encrypted flash on ESP8266, physical device extraction exposes the broker password.

### 6. SSH Access Policy & Key Enforcement Deficit
- **Permissive Authentication**: While operator public keys are authorized in `~/.ssh/authorized_keys`, password authentication remains active (`PasswordAuthentication yes` in `/etc/ssh/sshd_config`) on both the VPS and Raspberry Pi gateway.
- **Brute-Force Attack Surface**: In the absence of an active firewall or Fail2ban jail, port 22 is continuously vulnerable to automated SSH dictionary sweeps.
- **Remedy**: Enforce `PasswordAuthentication no` on all production hosts and restrict SSH ingress to Tailscale network interfaces or trusted IP ranges.
