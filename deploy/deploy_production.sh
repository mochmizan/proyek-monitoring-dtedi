#!/usr/bin/env bash
# ==============================================================================
# SMSB Central Server Production Deployment Script (Milestone 10)
#
# Execution Pipeline:
#   Step 1: Pre-flight Environment Auditing (tools/verify_prod_env.py)
#   Step 2: Frontend SPA Production Build (npm run build)
#   Step 3: Additive Database Migrations (server/init_sqlv5.py)
#   Step 4: Nginx Same-Origin Topology Configuration & Validation (nginx -t)
#   Step 5: Systemd / Uvicorn Service Reload & Live Verification
#
# Usage:
#   sudo bash deploy/deploy_production.sh [OPTIONS]
# Options:
#   --skip-env-check   Skip strict production .env audit (staging/dev only)
#   --allow-localhost  Allow localhost in URLs during pre-flight check
#   --no-service       Do not restart systemd service (only build & config)
#   -h, --help         Display this help message
# ==============================================================================

set -euo pipefail

# Terminal formatting
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_DIR="${REPO_ROOT}/server"
FRONTEND_DIR="${REPO_ROOT}/dashboard"
NGINX_CONF_SRC="${REPO_ROOT}/deploy/nginx_smsb.conf"
NGINX_CONF_DEST="/etc/nginx/sites-available/smsb"
SYSTEMD_SERVICE_DEST="/etc/systemd/system/hubgate.service"

SKIP_ENV_CHECK=false
ALLOW_LOCALHOST=false
RELOAD_SERVICE=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-env-check)
            SKIP_ENV_CHECK=true
            shift
            ;;
        --allow-localhost)
            ALLOW_LOCALHOST=true
            shift
            ;;
        --no-service)
            RELOAD_SERVICE=false
            shift
            ;;
        -h|--help)
            echo "Usage: sudo bash $0 [OPTIONS]"
            echo "Options:"
            echo "  --skip-env-check   Bypass strict .env audit"
            echo "  --allow-localhost  Allow localhost in URLs for local testing"
            echo "  --no-service       Skip systemd service restart"
            echo "  -h, --help         Show help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}${BOLD}====================================================================${NC}"
echo -e "${CYAN}${BOLD}    SMSB Central Server Production Deployment (Milestone 10)         ${NC}"
echo -e "${CYAN}${BOLD}====================================================================${NC}"
echo -e "Repository root: ${REPO_ROOT}"

# ------------------------------------------------------------------------------
# STEP 1: PRE-FLIGHT ENVIRONMENT CHECKS (Task 10.2)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 1/5] Running Pre-Flight Environment Checks...${NC}"

if [[ "${SKIP_ENV_CHECK}" = true ]]; then
    echo -e "${YELLOW}[WARN] Skipping environment audit (--skip-env-check specified).${NC}"
else
    ENV_CHECK_ARGS=("--target" "server" "--mode" "prod")
    if [[ "${ALLOW_LOCALHOST}" = true ]]; then
        ENV_CHECK_ARGS+=("--allow-localhost")
    fi

    if python3 "${REPO_ROOT}/tools/verify_prod_env.py" "${ENV_CHECK_ARGS[@]}"; then
        echo -e "${GREEN}[PASS] Pre-flight environment check passed.${NC}"
    else
        echo -e "\n${RED}[FAIL] Pre-flight environment check failed! Refusing to deploy insecure configuration.${NC}"
        echo -e "${RED}Fix the reported issues in server/.env or pass --allow-localhost if testing locally.${NC}"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# STEP 2: BUILD FRONTEND SPA (Task 10.1)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 2/5] Building Frontend React SPA...${NC}"

cd "${FRONTEND_DIR}"
if [[ ! -d "node_modules" ]]; then
    echo -e "${BLUE}[*] Installing Node dependencies...${NC}"
    npm ci || npm install
fi

echo -e "${BLUE}[*] Executing Vite production build...${NC}"
npm run build

if [[ ! -f "${FRONTEND_DIR}/dist/index.html" ]]; then
    echo -e "${RED}[FAIL] Frontend build failed: ${FRONTEND_DIR}/dist/index.html not found!${NC}"
    exit 1
fi
echo -e "${GREEN}[PASS] Frontend SPA built successfully at ${FRONTEND_DIR}/dist${NC}"

# ------------------------------------------------------------------------------
# STEP 3: PYTHON VENV & ADDITIVE DATABASE MIGRATIONS (Task 10.3)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 3/5] Applying Database Migrations & Python Dependencies...${NC}"

cd "${SERVER_DIR}"
if [[ ! -d "venv" ]]; then
    echo -e "${BLUE}[*] Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate
pip install -r requirements.txt --quiet

echo -e "${BLUE}[*] Running additive database schema migrations (init_sqlv5.py)...${NC}"
python init_sqlv5.py

echo -e "${GREEN}[PASS] Database schema is up to date.${NC}"

# ------------------------------------------------------------------------------
# STEP 4: NGINX CONFIGURATION & SSL SETUP (Task 10.1)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 4/5] Configuring Nginx Same-Origin Topology...${NC}"

# Ensure SSL certificates exist (generate self-signed fallback if missing)
CERT_KEY="${SERVER_DIR}/cert.key"
CERT_CRT="${SERVER_DIR}/cert.crt"
if [[ ! -f "${CERT_KEY}" ]] || [[ ! -f "${CERT_CRT}" ]]; then
    echo -e "${YELLOW}[*] Generating self-signed TLS certificate...${NC}"
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout "${CERT_KEY}" \
      -out "${CERT_CRT}" \
      -subj "/CN=${SERVER_IP}" \
      -addext "subjectAltName=IP:${SERVER_IP},DNS:localhost"
    chmod 600 "${CERT_KEY}"
fi

# Ensure static upload directories exist with proper permissions
mkdir -p "${SERVER_DIR}/static/uploads/floorplans"
chmod -R 755 "${SERVER_DIR}/static"

# Customize and install Nginx configuration
if [[ -d "/etc/nginx" ]]; then
    echo -e "${BLUE}[*] Installing ${NGINX_CONF_DEST}...${NC}"
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

    # Template paths replacement
    sed -e "s|/opt/smsb|${REPO_ROOT}|g" "${NGINX_CONF_SRC}" > "${NGINX_CONF_DEST}"

    # Symlink to sites-enabled
    ln -sf "${NGINX_CONF_DEST}" /etc/nginx/sites-enabled/smsb
    # Remove default site if it conflicts
    rm -f /etc/nginx/sites-enabled/default

    echo -e "${BLUE}[*] Testing Nginx configuration syntax (nginx -t)...${NC}"
    nginx -t
    
    echo -e "${BLUE}[*] Reloading Nginx...${NC}"
    systemctl reload nginx || systemctl restart nginx
    echo -e "${GREEN}[PASS] Nginx same-origin topology active.${NC}"
else
    echo -e "${YELLOW}[WARN] /etc/nginx not found (skipping system Nginx installation).${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 5: SYSTEMD SERVICE SETUP & SERVICE RESTART (Task 10.4)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}${BOLD}[Step 5/5] Managing HubGate Systemd Service...${NC}"

if [[ -d "/etc/systemd/system" ]] && [[ "${RELOAD_SERVICE}" = true ]]; then
    # Create / Update systemd unit file
    cat << EOF > "${SYSTEMD_SERVICE_DEST}"
[Unit]
Description=HubGate V5 Central Server API (FastAPI/Uvicorn)
After=network.target postgresql.service

[Service]
Type=simple
User=${SUDO_USER:-$(whoami)}
WorkingDirectory=${SERVER_DIR}
Environment="PATH=${SERVER_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=${SERVER_DIR}/venv/bin/uvicorn app.main:api --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

    echo -e "${BLUE}[*] Reloading systemd daemon and restarting hubgate.service...${NC}"
    systemctl daemon-reload
    systemctl enable hubgate.service
    systemctl restart hubgate.service
    systemctl status hubgate.service --no-pager --lines=5

    echo -e "${GREEN}[PASS] HubGate V5 central service is running.${NC}"
else
    echo -e "${YELLOW}[*] Skipping systemd service reload (run uvicorn manually if required).${NC}"
fi

echo -e "\n${CYAN}${BOLD}====================================================================${NC}"
echo -e "${GREEN}${BOLD} [SUCCESS] Production Central Server Deployment Complete!            ${NC}"
echo -e "${CYAN}${BOLD}====================================================================${NC}"
echo -e "Central Server is serving same-origin on Port 443 (HTTPS) and Port 80 (HTTP redirect)."
echo -e "To verify the live deployment, run:"
echo -e "  ${BOLD}python tools/verify_production_deployment.py --base-url https://<SERVER_IP> --insecure${NC}\n"

exit 0
