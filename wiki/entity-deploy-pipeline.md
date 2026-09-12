---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-devops-infrastructure.md, wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-production-readiness.md, wiki/workstream-production-grade-roadmap.md]
sources: [deploy/setup_push_deploy.sh, deploy/smsb-api.service, deploy/nginx_smsb.conf, deploy/AGENTS.md, tools/rotate_credentials.py, commit:acd4f00, commit:6bf89e6]
updated: 2026-09-03
---

# Deploy Pipeline & Release Operations

The SMSB deployment pipeline manages source code synchronization, automated runtime builds, service recycling, and cryptographic credential rotation between development workstations, the central cloud server, and edge gateways.

---

## 1. Push-to-Deploy Architecture & Pipeline Mechanics

Production deployment executes via Git transport over SSH to the bare repository located at:
```bash
git push prod main
# Remote: ssh://genset@100.108.98.30/opt/smsb.git
```

```
+------------------+          +--------------------------------------------------+
| Local Dev / Host |          | Central VPS (genset, 100.108.98.30)              |
|                  |          |                                                  |
| git push prod    | -------> | /opt/smsb.git (Bare Repo)                        |
| main             |   SSH    |   |                                              |
+------------------+          |   +---> hooks/post-receive                       |
                              |           |                                      |
                              |           v                                      |
                              |         /opt/smsb (Work Tree Clone)              |
                              |           1. git fetch && git reset --hard main  |
                              |           2. pip install requirements.txt        |
                              |           3. npm ci && npm run build             |
                              |           4. rsync dist/ -> /var/www/gui-app     |
                              |           5. sudo systemctl restart smsb-api     |
                              |           6. Automated Smoke Checks              |
                              +--------------------------------------------------+
```

### Permission Boundaries & Identity Segregation
The pipeline enforces strict privilege separation between deployment operations and service execution:
- **Deploy User (`genset`)**: Owns the bare repo `/opt/smsb.git`. Possesses SSH public-key access. Owns files in the work tree `/opt/smsb` under group `smsb` with group write permissions (`g+rwX`) and setgid directories (`chmod g+s`).
- **Service User (`smsb`)**: Unprivileged system user with no login shell. Executes Uvicorn/FastAPI. Strictly owns the production environment file (`/opt/smsb/server/.env`) and SQLite database files (`/opt/smsb/server/hubgatev5.db*`) with mode `600`/`660`. A blanket `chown -R genset:genset` causes immediate SQLite permission failures (`sqlite3.OperationalError: attempt to write a readonly database`).
- **Sudoers Scope**: Sudo authorization is strictly bounded via `/etc/sudoers.d/smsb-deploy`:
  ```sudoers
  genset ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart smsb-api.service
  ```
  The deploy user possesses no root shell access or broader systemctl privileges.

### Post-Receive Hook Workflow (`deploy/setup_push_deploy.sh`)
When changes are pushed to `refs/heads/main`, the hook executes the following deterministic sequence:
1. **Branch Filter**: Verifies the pushed ref is `refs/heads/main`. Pushes to other branches are skipped.
2. **Work Tree Synchronization**: Captures previous commit hash (`oldrev=$(git rev-parse HEAD)`), clears Git environment variables (`unset GIT_DIR GIT_WORK_TREE`), and executes `git fetch origin main && git reset --hard origin/main`.
3. **Python Dependency Resolution**: Executes `/opt/smsb/venv/bin/pip install --quiet -r server/requirements.txt` into the virtual environment.
4. **Pre-Flight Python Verification & Automated Rollback**:
   - Compiles server sources: `python -m compileall -q server/`.
   - Verifies application import: `from app.main import api`.
   - **Automated Rollback to `oldrev`**: If either compileall or app import fails, the hook automatically reverts the work tree (`git reset --hard "${oldrev}"`) and aborts deployment without modifying or restarting the running service.
5. **Dashboard SPA Compilation**: Sources NVM for Node 22 (`[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" && nvm use 22`) and builds the React 19 / Vite SPA:
   ```bash
   cd /opt/smsb/dashboard && npm ci --ignore-engines && npm run build --ignore-engines
   ```
6. **Atomic Web Asset Publishing**: Synchronizes Vite build output directly to the Nginx root directory via `rsync -a --delete /opt/smsb/dashboard/dist/ /var/www/gui-app/`.
7. **Backend Service Restart**: Executes `sudo -n systemctl restart smsb-api.service`.
8. **Post-Deploy Smoke Verification**:
   - **API Health Probe Gate**: Polls `https://127.0.0.1/api/health` for up to 20 seconds, asserting `HTTP 200 OK` and database connectivity (`status: ok`).
   - **Auth Gate**: Polls `https://127.0.0.1/api/auth/me` unauthenticated for up to 20 seconds; asserts that the endpoint returns `HTTP 401 Unauthorized`.
   - **SPA Asset Gate**: Queries `https://127.0.0.1/` and verifies the HTML body contains the `<title>` tag.
   - **Systemd Liveness Gate**: Confirms `systemctl is-active --quiet smsb-api` returns 0.
9. **Rollback Guidance**: If post-restart smoke checks fail, the hook prints actionable manual rollback commands and exits with status 1.

### Historical Pipeline Normalization (2026-09-03)
Historically, prior to 2026-08-31, an omission in the rsync step resulted in backend pushes silently deploying nothing while frontend builds appeared fresh. On 2026-09-03, runtime paths were permanently normalized:
- The legacy execution path `/opt/smsb/SERVERv5/v5` and intermediate rsync compatibility overlay were decommissioned.
- `smsb-api.service` was updated with canonical `WorkingDirectory=/opt/smsb/server` and systemd daemon-reloaded.
- Server code now executes in-place directly from the worktree clone.

### Operational Constraint: Hook In-Place Synchronization
Pushing an updated `deploy/setup_push_deploy.sh` to the Git repository **does not automatically update the active hook** at `/opt/smsb.git/hooks/post-receive`. To apply pipeline script modifications, operators must:
1. SSH to the VPS host: `ssh genset@100.108.98.30`.
2. Re-execute the bootstrap script with root privileges: `sudo bash /opt/smsb/deploy/setup_push_deploy.sh --yes`.

---

## 2. Secrets & Credential Rotation Runbook

System credentials across web users, gateway API tokens, MQTT brokers, and microcontroller firmware are rotated using `tools/rotate_credentials.py`.

```
                +------------------------------------+
                |  tools/rotate_credentials.py CLI   |
                +------------------------------------+
                                  |
         +------------------------+------------------------+
         |                        |                        |
         v                        v                        v
+------------------+     +------------------+     +------------------+
| Central Database |     |  Server Secrets  |     | Edge Gateway Pi  |
| - Argon2id Users |     |  - server/.env   |     | - hub/.env       |
| - Flush Sessions |     |    HUB_KEY       |     | - Mosquitto      |
| - hub_table Key  |     +------------------+     |   passwd         |
+------------------+                              +------------------+
                                                           |
                                                           v
                                                  +------------------+
                                                  | ESP8266 Firmware |
                                                  | - secrets.h      |
                                                  |   MQTT_PASS      |
                                                  +------------------+
```

### Multi-Tier Rotation Procedure

#### Step 1: Central Server Rotation
Execute the rotation CLI on the central server (or with remote DB connection):
```bash
python tools/rotate_credentials.py \
    --target-db /opt/smsb/server/hubgatev5.db \
    --update-env /opt/smsb/server/.env \
    --hub-id hs109rs-hub-01
```
CLI options and operational behaviors:
- `--dry-run`: Generates and prints passwords and tokens without writing to the database or updating `.env`.
- `--keep-dev-logins`: Preserves default dev passwords (`admin123`, `operator123`, `viewer123`) while updating Argon2id salts and rotating the `HUB_KEY`.
- `--target-db <PATH_OR_URL>`: Supports SQLite database paths (`server/hubgatev5.db`) or PostgreSQL connection URIs (`postgresql://smsb_app:pass@127.0.0.1:5432/smsb_prod`).
- `--update-env <PATH>`: Replaces `HUB_KEY` in the target `.env` file while preserving existing comments and variable formatting.

Rotation effects on Central Server:
- Generates 24-character cryptographically secure passwords for `admin`, `operator`, and `viewer` using Argon2id hashing.
- Generates a 64-character hexadecimal `HUB_KEY`.
- Flushes the `sessions` and `login_attempts` tables, terminating all active user logins.
- Updates `hub_key` for `hs109rs-hub-01` in `hub_table`.
- Updates `HUB_KEY` in `/opt/smsb/server/.env`.
- Restart the API daemon: `sudo systemctl restart smsb-api`.
- Verify unauthenticated rejection: `curl -k https://127.0.0.1/api/auth/me` (expected: 401).

#### Step 2: Edge Gateway Synchronization
Connect to the Raspberry Pi gateway (`hubadmin@10.33.102.10`):
1. Update `/home/hubadmin/smsb/hub/.env` with the newly generated `HUB_KEY`:
   ```bash
   sed -i 's/^HUB_KEY=.*/HUB_KEY=<NEW_64_HEX_KEY>/' /home/hubadmin/smsb/hub/.env
   ```
2. Restart the ingestion service: `sudo systemctl restart hubbrain`.
3. Verify telemetry uplink in logs: `journalctl -u hubbrain -n 30 --no-pager | grep -i "SYNC"`.

#### Step 3: Mosquitto MQTT Credential Rotation (Optional)
If rotating edge broker credentials:
1. Generate new PBKDF2 hash on the Pi:
   ```bash
   python3 tools/generate_mosquitto_passwd.py --user hubadmin --password <NEW_MQTT_PASS> --file /etc/mosquitto/passwd
   ```
2. Reload broker: `sudo systemctl reload mosquitto`.
3. Update `MQTT_PASS` in `/home/hubadmin/smsb/hub/.env` and restart `hubbrain`.

#### Step 4: Microcontroller Firmware Synchronization
When `MQTT_PASS` is rotated:
1. Update `firmware/WEMOS_ATS/secrets.h`, `firmware/WEMOS_TS/secrets.h`, and `firmware/WEMOS_AC/secrets.h`:
   ```cpp
   #define MQTT_PASS "<NEW_MQTT_PASS>"
   ```
2. Recompile and reflash nodes via esptool or Arduino CLI.

#### Step 5: Host Operating System Passwords
1. Rotate VPS SSH user: `ssh genset@100.108.98.30 'passwd'`
2. Rotate Pi SSH user: `ssh hubadmin@10.33.102.10 'passwd'`

### Secrets Management: Development vs Production Posture
- **Development Environment**: Permits permissive fallback flags (`ALLOW_INSECURE_DEV_KEYS=true`), weak default passwords (`admin123`), and plain SQLite databases without Argon2id enforcement overhead.
- **Production Environment**: Enforces Argon2id password hashing, strict file permissions (mode `600`, owned by `smsb`), 64-character hex tokens, and fail-fast startup checks in `app.core.config` and `hub/main.py` that refuse to start if weak placeholders are detected.

### Post-Deployment Verification Runbook
Following any deployment or credential rotation, verify live system integrity using the automated verification suite:
```bash
python tools/verify_production_deployment.py --base-url https://100.108.98.30 --insecure
```
The suite verifies:
1. **TLS / Port 80 Redirect**: Confirms HTTP 80 returns `301 Permanent Redirect` to HTTPS 443.
2. **Security Headers**: Validates `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.
3. **SPA Asset Ingress**: Verifies `index.html` loads with `Cache-Control: no-cache` and hashed assets load with immutable 1-year cache headers.
4. **Authentication Endpoints**: Confirms `POST /api/auth/login` issues valid JWT session cookies and unauthenticated queries return `401 Unauthorized`.
5. **Telemetry Ingestion**: Dispatches authenticated test payloads with `X-Hub-ID` and `X-Hub-Key` to verify end-to-end database writes.

---

## 3. Operational Reality & Production Gaps

The current deployment pipeline possesses five critical production-grade gaps:

### 1. Ingestion & User Downtime During Restarts
- **Mechanism**: The hook restarts Uvicorn abruptly via `systemctl restart smsb-api.service`.
- **Impact**: Uvicorn cold start on the 1 GB VPS requires 2 to 5 seconds. During this window, incoming HTTP batch ingestions from edge gateways fail with `HTTP 502 Bad Gateway`. While HubBrain's offline WAL buffers telemetry, web users experience connection drops and chart polling errors.
- **Remedy Required**: Implement zero-downtime worker reloads (e.g. Uvicorn graceful worker reload or dual-process blue/green socket switching).

### 2. Pre-Flight Rollback vs Post-Restart Advisory Rollback
- **Mechanism**: Pre-flight Python syntax errors (`compileall`) and application import failures (`from app.main import api`) now trigger immediate automated rollback to `oldrev` via `git reset --hard "${oldrev}"` before the service is touched. However, if post-restart smoke checks fail (e.g. database schema mismatch during runtime), the hook prints rollback instructions and exits with code 1.
- **Impact**: Pre-flight failures are cleanly averted with zero downtime. For post-restart runtime failures, the broken service remains live until an operator manually intervenes.
- **Remedy Required**: Extend automated rollback and service recycling to the post-restart failure trap.

### 3. Missing Pre-Deployment Migration Safety Gate
- **Mechanism**: The Git hook runs `pip install` and `npm run build`, but completely skips database migrations (`server/init_sqlv5.py`).
- **Impact**: Pushing code with new database column requirements causes immediate SQL exceptions upon startup because the schema has not been updated ahead of code execution.
- **Remedy Required**: Execute pre-flight environment checks (`verify_prod_env.py`) and additive schema migrations (`init_sqlv5.py`) prior to triggering service reloads.

### 4. Host Resource Contention During In-Band Vite Builds
- **Mechanism**: The frontend SPA is compiled directly on the production VPS using `npm run build` inside the post-receive hook.
- **Impact**: Vite compilation on Node 22 spikes CPU usage to 100% and memory consumption to > 500MB on a 1 GB VPS, risking OOM-kill of active backend processes.
- **Remedy Required**: Build production SPA bundles in CI/CD runners (e.g. GitHub Actions) and deploy pre-built tarball artifacts directly to the web root.

### 5. Omission of Pre-Flight Environment Auditing in Hook
- **Mechanism**: While `deploy/deploy_production.sh` executes `tools/verify_prod_env.py`, the active Git push hook `deploy/setup_push_deploy.sh` omits this step entirely.
- **Impact**: Misconfigured secrets or broken `.env` variables pushed to production bypass pre-flight audits and cause runtime crashes only after Uvicorn has restarted.
- **Remedy Required**: Integrate `python tools/verify_prod_env.py --target server --mode prod` into the post-receive hook sequence before dependency installs or restarts.
