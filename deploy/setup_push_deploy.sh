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
#        - npm ci && npm run build in apps/web (if node present)
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
SPA_DIR="${SPA_DIR:-${WORK_TREE}/apps/web}"
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
run "echo '${DEPLOY_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ${SERVICE_NAME}.service' > '${SUDOERS_PATH}'"
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
SPA_DIR="${DEPLOY_WORK_TREE}/apps/web"
WWW_DIR="/var/www/gui-app"
SERVICE_NAME="smsb-api"

while read -r _old _new ref; do
    branch="${ref#refs/heads/}"
    # Only deploy pushes to main
    if [[ "${branch}" != "main" ]]; then
        echo "[post-receive] skipping non-main ref '${ref}'"
        continue
    fi

    echo "[post-receive] deploying '${branch}' -> ${DEPLOY_WORK_TREE}"
    fail=0

    if ! ( cd "${DEPLOY_WORK_TREE}" && unset GIT_DIR GIT_WORK_TREE && git fetch origin "${branch}" && git reset --hard "origin/${branch}" ); then
        echo "[post-receive] ERROR: work-tree sync failed"
        exit 1
    fi

    # Python deps (only if venv was provisioned already)
    if [[ -x "${VENV_DIR}/bin/pip" ]]; then
        echo "[post-receive] pip install into ${VENV_DIR}"
        "${VENV_DIR}/bin/pip" install --quiet \
            -r "${DEPLOY_WORK_TREE}/server/requirements.txt" || fail=1
    else
        echo "[post-receive] NOTE: no venv at ${VENV_DIR}, skipping pip install"
    fi

    # SPA build + publish (only if node/npm available on the VPS)
    if command -v npm >/dev/null 2>&1; then
        echo "[post-receive] building SPA in ${SPA_DIR}"
        ( cd "${SPA_DIR}" && npm ci && npm run build ) || fail=1
        if [[ ${fail} -eq 0 && -d "${SPA_DIR}/dist" ]]; then
            mkdir -p "${WWW_DIR}"
            rsync -a --delete "${SPA_DIR}/dist/" "${WWW_DIR}/" || fail=1
        fi
    else
        echo "[post-receive] NOTE: npm not found, skipping SPA build (serving existing ${WWW_DIR})"
    fi

    # Restart API service (hook runs as the unprivileged deploy user;
    # sudoers rule authorizes exactly "systemctl restart <unit>.service")
    sudo -n systemctl restart "${SERVICE_NAME}.service" || fail=1
    sleep 2

    # ---- Post-deploy smoke checks -------------------------------------------
    echo "[post-receive] running smoke checks..."

    # Check 1: unauthenticated /api/auth/me must return 401.
    # Uvicorn can take several seconds to bind on the 1 GB VPS â€” poll for it.
    me_code="000"
    for _ in $(seq 1 20); do
        me_code="$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/auth/me || echo 000)"
        [[ "${me_code}" == "401" ]] && break
        sleep 1
    done
    if [[ "${me_code}" == "401" ]]; then
        echo "[post-receive] PASS: /api/auth/me returned 401"
    else
        echo "[post-receive] FAIL: /api/auth/me expected 401, got ${me_code}"
        fail=1
    fi

    # Check 2: SPA index served and contains <title>
    if curl -sk https://127.0.0.1/ | grep -qi '<title'; then
        echo "[post-receive] PASS: SPA index.html contains <title>"
    else
        echo "[post-receive] FAIL: SPA index.html missing <title>"
        fail=1
    fi

    # Check 3: service active
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "[post-receive] PASS: ${SERVICE_NAME} is active"
    else
        echo "[post-receive] FAIL: ${SERVICE_NAME} is NOT active"
        fail=1
    fi

    if [[ ${fail} -ne 0 ]]; then
        cat <<EOF

============================================================
[post-receive] DEPLOYMENT CHECKS FAILED.
Rollback hint (run as root on this VPS):
  # Find the last known-good commit:
  git --git-dir=/opt/smsb.git log --oneline -5
  # Re-sync the work tree clone to the previous commit:
  cd /opt/smsb && git fetch origin && git reset --hard origin/main~1
  # Rebuild/reinstall as needed, then:
  systemctl restart ${SERVICE_NAME}
  journalctl -u ${SERVICE_NAME} -n 50 --no-pager
============================================================
EOF
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
