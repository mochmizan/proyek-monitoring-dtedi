#!/usr/bin/env bash
# ==============================================================================
# setup_push_deploy.sh â€” One-time git push-to-deploy bootstrap for the VPS
#
# Run ON THE VPS ('genset') as root. Idempotent: safe to re-run.
# It:
#   1. Creates a bare git repo at /opt/smsb.git
#   2. Installs a post-receive hook that, on every `git push prod`:
#        - syncs /opt/smsb (an independent clone with origin=/opt/smsb.git)
#          via fetch + reset --hard origin/main
#        - pip-installs requirements into /opt/smsb/venv (if venv exists)
#        - npm ci && npm run build in dashboard (if node present)
#        - rsyncs dist/ to /var/www/gui-app
#        - restarts smsb-api.service
#        - runs post-deploy smoke checks (API 401 on /api/auth/me unauthenticated,
#          SPA index.html title, systemctl is-active smsb-api)
#        - prints a rollback hint if any step fails
#
# Usage (on VPS):
#   sudo bash setup_push_deploy.sh [--dry-run] [--yes]
#
# Usage (Windows dev machine, one-time remote setup â€” Tailscale IP works only
# from devices on the tailnet):
#   git remote add prod ssh://genset@100.108.98.30/opt/smsb.git
#   git push prod main
#
# NO SECRETS IN THIS FILE: SSH keys/auth are managed by the OS; nothing here
# embeds credentials.
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Tunables (override via env if layout changes) -----------------------------
DEPLOY_USER="${DEPLOY_USER:-genset}"
BARE_REPO="${BARE_REPO:-/opt/smsb.git}"
WORK_TREE="${WORK_TREE:-/opt/smsb}"
VENV_DIR="${VENV_DIR:-/opt/smsb/venv}"
SPA_DIR="${SPA_DIR:-${WORK_TREE}/dashboard}"
WWW_DIR="${WWW_DIR:-/var/www/gui-app}"
SERVICE_NAME="${SERVICE_NAME:-smsb-api}"

DRY_RUN=false
ASSUME_YES=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --yes)     ASSUME_YES=true ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}" >&2
            echo "Usage: sudo bash $0 [--dry-run] [--yes]" >&2
            exit 1 ;;
    esac
done

log()  { echo -e "${CYAN}[setup]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }

# Execute or print a command depending on dry-run mode.
run() {
    if [[ "${DRY_RUN}" = true ]]; then
        echo -e "${YELLOW}[dry-run]${NC} $*"
    else
        eval "$@"
    fi
}

if [[ "$(id -u)" -ne 0 ]]; then
    echo -e "${RED}ERROR: must run as root (sudo).${NC}" >&2
    exit 1
fi

log "Push-deploy bootstrap for SMSB"
log "  bare repo : ${BARE_REPO}"
log "  work tree : ${WORK_TREE}"
log "  venv      : ${VENV_DIR}"
log "  SPA dist  : ${WWW_DIR}"
log "  service   : ${SERVICE_NAME}"
log "  mode      : $( [[ "${DRY_RUN}" = true ]] && echo 'DRY-RUN (no changes)' || echo 'APPLY' )"

if [[ "${ASSUME_YES}" != true ]]; then
    read -r -p "Proceed with installation? [y/N] " reply
    case "${reply}" in
        y|Y|yes|YES) ;;
        *) echo "Aborted by user."; exit 1 ;;
    esac
fi

# ------------------------------------------------------------------------------
# 0. Active Swap Space Check & Provisioning (< 1GB -> 2GB /swapfile)
# ------------------------------------------------------------------------------
log "Checking active swap memory..."
swap_active_bytes=0
if command -v swapon >/dev/null 2>&1; then
    while read -r sz; do
        if [[ "${sz}" =~ ^[0-9]+$ ]]; then
            swap_active_bytes=$(( swap_active_bytes + sz ))
        fi
    done < <(swapon --show=SIZE --bytes --noheadings 2>/dev/null || swapon --show --bytes --noheadings 2>/dev/null | awk '{print $3}' || true)
fi

# Fallback to /proc/meminfo if swapon produced no numbers
if [[ "${swap_active_bytes}" -eq 0 ]] && [[ -f /proc/meminfo ]]; then
    swap_kb=$(awk '/SwapTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
    if [[ "${swap_kb}" =~ ^[0-9]+$ ]]; then
        swap_active_bytes=$(( swap_kb * 1024 ))
    fi
fi

ONE_GB_BYTES=1073741824
if [[ "${swap_active_bytes}" -lt "${ONE_GB_BYTES}" ]]; then
    warn "Active swap is $(( swap_active_bytes / 1024 / 1024 ))MB (< 1GB threshold). Provisioning 2GB /swapfile..."
    if [[ ! -f /swapfile ]]; then
        log "Allocating 2GB swapfile at /swapfile..."
        run "fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none"
        run "chmod 600 /swapfile"
        run "mkswap /swapfile"
    else
        log "Existing /swapfile found; securing permissions..."
        run "chmod 600 /swapfile"
    fi
    log "Activating swapfile..."
    run "swapon /swapfile || true"
    if ! grep -q '^/swapfile' /etc/fstab 2>/dev/null; then
        log "Appending /swapfile to /etc/fstab for persistence across reboots"
        run "bash -c 'echo \"/swapfile none swap sw 0 0\" >> /etc/fstab'"
    fi
    ok "2GB swap space provisioned and activated."
else
    ok "Active swap is $(( swap_active_bytes / 1024 / 1024 ))MB (>= 1GB threshold)."
fi

# ------------------------------------------------------------------------------
# 1. Bare repository
# ------------------------------------------------------------------------------
if [[ -d "${BARE_REPO}" ]]; then
    warn "${BARE_REPO} already exists â€” reusing it."
else
    log "Creating bare repo at ${BARE_REPO}"
    run "git init --bare '${BARE_REPO}'"
    run "chown -R '${DEPLOY_USER}:${DEPLOY_USER}' '${BARE_REPO}'"
fi

# ------------------------------------------------------------------------------
# 2. Ensure work tree and web root exist with sane ownership
# ------------------------------------------------------------------------------
run "mkdir -p '${WORK_TREE}' '${WWW_DIR}'"
# Group smsb everywhere + setgid dirs so service-created files stay group-accessible.
run "chown -R '${DEPLOY_USER}:smsb' '${WORK_TREE}'"
run "chmod -R g+rwX '${WORK_TREE}'"
run "find '${WORK_TREE}' -type d -exec chmod g+s {} +"
# Secrets & runtime state must stay owned by the SERVICE user (smsb writes the
# SQLite DB; a genset-owned .env/DB causes 'readonly database' HTTP 500s).
run "bash -c 'chown smsb:smsb \"${WORK_TREE}/server/.env\" \"${WORK_TREE}/server/hubgatev5.db\"* 2>/dev/null || true'"
# nginx reads but never writes the SPA root.
run "chmod 755 '${WWW_DIR}'"

# ------------------------------------------------------------------------------
# 3a. Sudoers: the post-receive hook runs unprivileged but must restart the API
# ------------------------------------------------------------------------------
SUDOERS_PATH="/etc/sudoers.d/smsb-deploy"
log "Installing sudoers rule: ${DEPLOY_USER} may restart ${SERVICE_NAME}"
run "echo '${DEPLOY_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${SERVICE_NAME}.service, /bin/systemctl restart ${SERVICE_NAME}.service' > '${SUDOERS_PATH}'"
run "chmod 440 '${SUDOERS_PATH}'"
run "visudo -c"

# ------------------------------------------------------------------------------
# 4. Post-receive hook
# ------------------------------------------------------------------------------
HOOK_PATH="${BARE_REPO}/hooks/post-receive"
HOOK_TMP="$(mktemp)"
trap 'rm -f "${HOOK_TMP}"' EXIT

log "Generating post-receive hook content..."
cat > "${HOOK_TMP}" <<'HOOK'
#!/usr/bin/env bash
# Auto-generated by deploy/setup_push_deploy.sh â€” do not hand-edit;
# re-run the setup script instead.
set -euo pipefail

DEPLOY_WORK_TREE="/opt/smsb"
VENV_DIR="/opt/smsb/venv"
SPA_DIR="${DEPLOY_WORK_TREE}/dashboard"
WWW_DIR="/var/www/gui-app"
SERVICE_NAME="smsb-api"

while read -r oldrev newrev ref; do
    branch="${ref#refs/heads/}"
    # Only deploy pushes to main
    if [[ "${branch}" != "main" ]]; then
        echo "[post-receive] skipping non-main ref '${ref}'"
        continue
    fi

    echo "[post-receive] deploying '${branch}' -> ${DEPLOY_WORK_TREE}"
    fail=0

    # Capture work-tree revision before update to enable rollback on pre-flight failure
    oldrev=$( cd "${DEPLOY_WORK_TREE}" && git rev-parse HEAD 2>/dev/null || echo "${oldrev}" )

    if ! ( cd "${DEPLOY_WORK_TREE}" && unset GIT_DIR GIT_WORK_TREE && git fetch origin "${branch}" && git reset --hard "origin/${branch}" ); then
        echo "[post-receive] ERROR: work-tree sync failed"
        exit 1
    fi

    # Python deps (only if venv was provisioned already)
    if [[ -x "${VENV_DIR}/bin/pip" ]]; then
        echo "[post-receive] pip install into ${VENV_DIR}"
        if ! "${VENV_DIR}/bin/pip" install --quiet \
            -r "${DEPLOY_WORK_TREE}/server/requirements.txt"; then
            echo "[post-receive] FATAL: pip install failed. Aborting deployment before service restart."
            exit 1
        fi
    else
        echo "[post-receive] NOTE: no venv at ${VENV_DIR}, skipping pip install"
    fi

    # Pre-flight Python verification before service restart:
    # Compile sources and verify app.main:api can be imported cleanly.
    # If this fails, revert the work tree and abort deployment without touching the running service!
    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        echo "[post-receive] pre-flight: compiling python sources..."
        if ! "${VENV_DIR}/bin/python" -m compileall -q "${DEPLOY_WORK_TREE}/server"; then
            echo "[post-receive] FATAL: Python syntax compilation error. Reverting work tree to ${oldrev}..."
            ( cd "${DEPLOY_WORK_TREE}" && git reset --hard "${oldrev}" )
            echo "[post-receive] Aborting deployment without modifying running service."
            exit 1
        fi

        echo "[post-receive] pre-flight: verifying application import (app.main:api)..."
        if ! ( cd "${DEPLOY_WORK_TREE}/server" && "${VENV_DIR}/bin/python" -c "from app.main import api; print('[post-receive] App import verified (app.main:api).')" ); then
            echo "[post-receive] FATAL: Application import verification failed (app.main:api). Reverting work tree to ${oldrev}..."
            ( cd "${DEPLOY_WORK_TREE}" && git reset --hard "${oldrev}" )
            echo "[post-receive] Aborting deployment without modifying running service."
            exit 1
        fi

        echo "[post-receive] pre-flight: applying database migrations (alembic upgrade head)..."
        if ! ( cd "${DEPLOY_WORK_TREE}/server" && "${VENV_DIR}/bin/python" -m alembic upgrade head ); then
            echo "[post-receive] FATAL: Database migration failed (alembic upgrade head). Reverting work tree to ${oldrev}..."
            ( cd "${DEPLOY_WORK_TREE}" && git reset --hard "${oldrev}" )
            echo "[post-receive] Aborting deployment without modifying running service."
            exit 1
        fi
    else
        echo "[post-receive] NOTE: no python at ${VENV_DIR}/bin/python, skipping python pre-flight"
    fi

    # SPA build + publish (only if node/npm available on the VPS)
    # Strictly gate asset sync: only replace ${WWW_DIR} if npm run build succeeds with exit code 0.
    if command -v npm >/dev/null 2>&1; then
        echo "[post-receive] building SPA in ${SPA_DIR}..."
        # Use nvm Node 22 if available (Vite 8 requires Node 20.19+/22), else fallback to system npm with engine-strict false
        if [ -s "$HOME/.nvm/nvm.sh" ]; then \. "$HOME/.nvm/nvm.sh" && nvm use 22 >/dev/null 2>&1 || true; fi
        npm config set engine-strict false >/dev/null 2>&1 || true
        export NODE_OPTIONS="--max-old-space-size=2048"

        spa_build_ok=0
        if ( cd "${SPA_DIR}" && npm ci --ignore-engines && npm run build --ignore-engines ); then
            spa_build_ok=1
        fi

        if [[ ${spa_build_ok} -eq 1 && -d "${SPA_DIR}/dist" ]]; then
            echo "[post-receive] SPA build succeeded. Syncing assets to ${WWW_DIR}..."
            mkdir -p "${WWW_DIR}"
            rsync -a --delete "${SPA_DIR}/dist/" "${WWW_DIR}/" || {
                echo "[post-receive] ERROR: Failed to rsync SPA assets to ${WWW_DIR}"
                fail=1
            }
            chmod -R 755 "${WWW_DIR}" || true
        else
            echo "[post-receive] ERROR: SPA build failed with non-zero exit code. Skipping asset sync to ${WWW_DIR} to preserve live frontend."
            fail=1
        fi
    else
        echo "[post-receive] NOTE: npm not found, skipping SPA build (serving existing ${WWW_DIR})"
    fi

    # Restart the service directly (standalone uvicorn does not handle SIGHUP reload)
    echo "[post-receive] restarting service (${SERVICE_NAME}.service)..."
    sudo -n systemctl restart "${SERVICE_NAME}.service" || fail=1
    sleep 2

    # ---- Post-deploy smoke checks -------------------------------------------
    echo "[post-receive] running smoke checks..."

    # Check 1: API health probe (/api/health)
    # Poll for up to 20 seconds to allow uvicorn worker bind
    health_ok=0
    health_status="000"
    health_body=""
    for _ in $(seq 1 20); do
        health_resp=$(curl -sk -w "\nHTTP_STATUS:%{http_code}" https://127.0.0.1/api/health 2>&1 || true)
        health_status=$(echo "${health_resp}" | grep "HTTP_STATUS:" | cut -d':' -f2 || echo "000")
        health_body=$(echo "${health_resp}" | grep -v "HTTP_STATUS:" || true)
        if [[ "${health_status}" == "200" ]] && echo "${health_body}" | grep -q '"status":"ok"'; then
            health_ok=1
            break
        fi
        sleep 1
    done

    if [[ ${health_ok} -eq 1 ]]; then
        echo "[post-receive] PASS: /api/health returned 200 OK (${health_body})"
    else
        echo "[post-receive] FAIL: /api/health check failed after 20 attempts"
        echo "[post-receive]   Last HTTP status: ${health_status:-none}"
        echo "[post-receive]   Response body / error: ${health_body:-empty}"
        fail=1
    fi

    # Check 2: unauthenticated /api/auth/me must return 401
    me_resp=$(curl -sk -w "\nHTTP_STATUS:%{http_code}" https://127.0.0.1/api/auth/me 2>&1 || true)
    me_status=$(echo "${me_resp}" | grep "HTTP_STATUS:" | cut -d':' -f2 || echo "000")
    me_body=$(echo "${me_resp}" | grep -v "HTTP_STATUS:" || true)
    if [[ "${me_status}" == "401" ]]; then
        echo "[post-receive] PASS: /api/auth/me returned 401 Unauthorized"
    else
        echo "[post-receive] FAIL: /api/auth/me expected 401, got ${me_status:-000}"
        echo "[post-receive]   Response body / error: ${me_body:-empty}"
        fail=1
    fi

    # Check 3: SPA index served and contains <title>
    spa_resp=$(curl -sk -w "\nHTTP_STATUS:%{http_code}" https://127.0.0.1/ 2>&1 || true)
    spa_status=$(echo "${spa_resp}" | grep "HTTP_STATUS:" | cut -d':' -f2 || echo "000")
    spa_body=$(echo "${spa_resp}" | grep -v "HTTP_STATUS:" || true)
    if echo "${spa_body}" | grep -qi '<title'; then
        echo "[post-receive] PASS: SPA index.html contains <title>"
    else
        echo "[post-receive] FAIL: SPA index.html missing <title> (HTTP ${spa_status:-000})"
        echo "[post-receive]   Response head: $(echo "${spa_body}" | head -n 5)"
        fail=1
    fi

    # Check 4: service active
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "[post-receive] PASS: ${SERVICE_NAME} is active"
    else
        echo "[post-receive] FAIL: ${SERVICE_NAME} is NOT active"
        fail=1
    fi

    if [[ ${fail} -ne 0 ]]; then
        echo ""
        echo "============================================================"
        echo "[post-receive] DEPLOYMENT CHECKS FAILED."
        echo "[post-receive] Diagnostic Information:"
        echo "--- systemctl status ${SERVICE_NAME} ---"
        systemctl status "${SERVICE_NAME}.service" --no-pager -l 2>&1 || true
        echo "--- journalctl -u ${SERVICE_NAME} (last 30 lines) ---"
        journalctl -u "${SERVICE_NAME}.service" -n 30 --no-pager 2>&1 || true
        echo "------------------------------------------------------------"
        echo "Rollback hint (run as root on this VPS):"
        echo "  # Find the last known-good commit:"
        echo "  git --git-dir=/opt/smsb.git log --oneline -5"
        echo "  # Re-sync the work tree clone to the previous commit:"
        echo "  cd /opt/smsb && git fetch origin && git reset --hard origin/main~1"
        echo "  # Rebuild/reinstall as needed, then:"
        echo "  systemctl restart ${SERVICE_NAME}"
        echo "  journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
        echo "============================================================"
        exit 1
    fi

    echo "[post-receive] deployment OK (${branch})"
done
HOOK

if [[ "${DRY_RUN}" = true ]]; then
    echo -e "${YELLOW}[dry-run]${NC} would install hook to ${HOOK_PATH}. Hook content:"
    echo "-----8<----- hook preview -----8<-----"
    cat "${HOOK_TMP}"
    echo "----->8----- end preview ----->8-----"
else
    log "Installing post-receive hook at ${HOOK_PATH}"
    install -m 0755 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${HOOK_TMP}" "${HOOK_PATH}"
fi

ok "Done."
log "Next steps:"
log "  1. From each Windows dev machine (on the tailnet):"
log "       git remote add prod ssh://${DEPLOY_USER}@100.108.98.30${BARE_REPO}"
log "  2. Deploy:  git push prod main"
log "  3. Watch:   ssh ${DEPLOY_USER}@100.108.98.30 'journalctl -u ${SERVICE_NAME} -f'"
