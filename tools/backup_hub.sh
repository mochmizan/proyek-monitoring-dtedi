#!/usr/bin/env bash
# ==============================================================================
# HubBrain V5 Edge Gateway - Mandatory Backup Gate Script
# 
# Purpose: Creates a timestamped, gzip-compressed tarball containing all critical
#          edge configurations (NetworkManager, hostapd, dnsmasq, Mosquitto, 
#          systemd service units, .env secrets, TLS certificates).
#
# Usage:
#   sudo bash tools/backup_hub.sh [--out-dir /path/to/backups] [--app-dir /path/to/smsb]
# ==============================================================================

set -euo pipefail

# ANSI Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}================================================================${NC}"
echo -e "${CYAN}${BOLD}    HubBrain Edge Gateway - Mandatory Backup Gate (Milestone 9) ${NC}"
echo -e "${CYAN}${BOLD}================================================================${NC}"

# Parse command line arguments
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUT_DIR="${BACKUP_DIR:-${HOME}/backups}"
APP_DIR="${REPO_ROOT}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out-dir)
            OUT_DIR="$2"
            shift 2
            ;;
        --app-dir)
            APP_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --out-dir DIR   Target directory for backup archives (default: \$HOME/backups)"
            echo "  --app-dir DIR   Path to SMSB repository root (default: auto-detected)"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            exit 1
            ;;
    esac
done

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
ARCHIVE_NAME="hubbrain_backup_${TIMESTAMP}.tar.gz"
mkdir -p "${OUT_DIR}"
ARCHIVE_PATH="${OUT_DIR}/${ARCHIVE_NAME}"
SHA_PATH="${ARCHIVE_PATH}.sha256"

echo -e "${BLUE}[*] Target archive:${NC} ${ARCHIVE_PATH}"
echo -e "${BLUE}[*] Checking files and directories to archive...${NC}"

# Collect files/directories that exist
CANDIDATE_ITEMS=(
    "/etc/NetworkManager/system-connections"
    "/etc/hostapd/hostapd.conf"
    "/etc/dnsmasq.conf"
    "/etc/dnsmasq.d"
    "/etc/mosquitto"
    "/etc/systemd/system/hubbrain.service"
    "${APP_DIR}/HUBV5/V5/.env"
    "${APP_DIR}/HUBV5/V5/cert.crt"
    "${APP_DIR}/HUBV5/V5/edge_cache.db"
)

# Also glob for any hubbrain*.service units in systemd
for s_unit in /etc/systemd/system/hubbrain*.service; do
    if [[ -f "${s_unit}" ]]; then
        CANDIDATE_ITEMS+=("${s_unit}")
    fi
done

ITEMS_TO_BACKUP=()
for item in "${CANDIDATE_ITEMS[@]}"; do
    if [[ -e "${item}" ]]; then
        # Deduplicate
        if [[ ! " ${ITEMS_TO_BACKUP[*]} " =~ " ${item} " ]]; then
            ITEMS_TO_BACKUP+=("${item}")
            echo -e "  ${GREEN}[+] Found:${NC} ${item}"
        fi
    else
        echo -e "  ${YELLOW}[-] Skipped (not found):${NC} ${item}"
    fi
done

if [[ ${#ITEMS_TO_BACKUP[@]} -eq 0 ]]; then
    echo -e "${RED}[ERROR] No critical configuration items found to back up!${NC}"
    exit 1
fi

echo -e "\n${BLUE}[*] Creating compressed tar archive...${NC}"

# Create tar archive using absolute paths with -P (preserve absolute pathnames)
# or standard tar with warning suppression
tar -czf "${ARCHIVE_PATH}" -P "${ITEMS_TO_BACKUP[@]}"

# ------------------------------------------------------------------------------
# STEP 2: VERIFICATION & INTEGRITY CHECKS (Task 9.3)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[*] Running integrity verification on backup archive...${NC}"

# Check 1: File size > 0
if [[ ! -s "${ARCHIVE_PATH}" ]]; then
    echo -e "${RED}[FAIL] Archive file is empty (0 bytes) or was not created!${NC}"
    rm -f "${ARCHIVE_PATH}"
    exit 1
fi

ARCHIVE_SIZE_BYTES=$(wc -c < "${ARCHIVE_PATH}" | tr -d ' ')
ARCHIVE_SIZE_HUMAN=$(du -h "${ARCHIVE_PATH}" | cut -f1)

# Check 2: tar -tzf integrity check
echo -e "${BLUE}[*] Verifying tar table of contents (tar -tzf)...${NC}"
if ! tar -tzf "${ARCHIVE_PATH}" > /dev/null 2>&1; then
    echo -e "${RED}[FAIL] tar -tzf integrity check failed! Archive is corrupted.${NC}"
    rm -f "${ARCHIVE_PATH}"
    exit 1
fi

# Compute SHA256 checksum
if command -v sha256sum >/dev/null 2>&1; then
    SHA256_VAL=$(sha256sum "${ARCHIVE_PATH}" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
    SHA256_VAL=$(shasum -a 256 "${ARCHIVE_PATH}" | awk '{print $1}')
else
    SHA256_VAL="N/A (sha256 utility not found)"
fi

echo "${SHA256_VAL}  ${ARCHIVE_NAME}" > "${SHA_PATH}"

echo -e "${GREEN}${BOLD}[PASS] Backup archive created and verified successfully!${NC}"
echo -e "  ${BOLD}Location:${NC} ${ARCHIVE_PATH}"
echo -e "  ${BOLD}Size:${NC}     ${ARCHIVE_SIZE_HUMAN} (${ARCHIVE_SIZE_BYTES} bytes)"
echo -e "  ${BOLD}SHA256:${NC}   ${SHA256_VAL}"
echo -e "  ${BOLD}Checksum File:${NC} ${SHA_PATH}"

# List archive table of contents
echo -e "\n${CYAN}${BOLD}=== Archive Contents Table ===${NC}"
tar -tzvf "${ARCHIVE_PATH}"

# ------------------------------------------------------------------------------
# STEP 3: OFF-DEVICE EXPORT INSTRUCTIONS (Tasks 9.2, 9.3)
# ------------------------------------------------------------------------------
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<PI_IP>")
PI_USER="${USER:-pi}"

echo -e "\n${YELLOW}${BOLD}================================================================${NC}"
echo -e "${YELLOW}${BOLD} [MANDATORY GATE] COPY BACKUP OFF-DEVICE BEFORE DEPLOYING!     ${NC}"
echo -e "${YELLOW}${BOLD}================================================================${NC}"
echo -e "Do NOT proceed with HubBrain deployment until this backup file is safely"
echo -e "stored on your local machine or external backup storage.\n"
echo -e "Run ONE of the following commands from your ${BOLD}LOCAL MACHINE / LAPTOP${NC}:"
echo -e ""
echo -e "  ${CYAN}# Option A: Secure Copy (SCP)${NC}"
echo -e "  ${BOLD}scp ${PI_USER}@${PI_IP}:${ARCHIVE_PATH} ./backups/${NC}"
echo -e "  ${BOLD}scp ${PI_USER}@${PI_IP}:${SHA_PATH} ./backups/${NC}"
echo -e ""
echo -e "  ${CYAN}# Option B: Rsync over SSH${NC}"
echo -e "  ${BOLD}rsync -avz -P ${PI_USER}@${PI_IP}:${ARCHIVE_PATH} ./backups/${NC}"
echo -e ""
echo -e "  ${CYAN}# Option C: Verify Checksum on Local Machine after download${NC}"
echo -e "  ${BOLD}cd ./backups && sha256sum -c ${ARCHIVE_NAME}.sha256${NC}"
echo -e "${YELLOW}================================================================${NC}\n"

exit 0
