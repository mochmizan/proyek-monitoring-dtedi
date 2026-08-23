#!/bin/bash

# Warna Terminal
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}      AUDIT KEAMANAN LOKAL HUBGATE / HUBBRAIN V5    ${NC}"
echo -e "${BLUE}====================================================${NC}\n"

# 1. PERIKSA IZIN FILE SENSITIF (.env, cert.key, passwd)
echo -e "${YELLOW}[1/3] Memeriksa Izin Berkas Sensitif (Target: 600 / -rw-------)...${NC}"

check_perm() {
    local FILE=$1
    if [ -f "$FILE" ]; then
        PERM=$(stat -c "%a" "$FILE")
        if [ "$PERM" -eq 600 ]; then
            echo -e "  [${GREEN}OK${NC}] $FILE -> Permission: $PERM (Aman)"
        else
            echo -e "  [${RED}WARN${NC}] $FILE -> Permission: $PERM (Sangat disarankan: chmod 600 $FILE)"
        fi
    else
        echo -e "  [${YELLOW}INFO${NC}] $FILE -> File tidak ditemukan di direktori ini."
    fi
}

check_perm ".env"
check_perm "cert.key"
check_perm "cert.crt"
check_perm "/etc/mosquitto/passwd"

echo ""

# 2. PERIKSA STATUS FIREWALL (UFW)
echo -e "${YELLOW}[2/3] Memeriksa Status Firewall (UFW)...${NC}"
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(sudo ufw status | grep "Status:" | awk '{print $2}')
    if [ "$UFW_STATUS" == "active" ]; then
        echo -e "  [${GREEN}OK${NC}] UFW Firewall AKTIF."
        
        # Cek apakah port 8000 terbuka secara tidak sengaja di UFW
        if sudo ufw status | grep -q "8000"; then
            echo -e "  [${RED}WARNING${NC}] Port 8000 terbuka di UFW! Disarankan ditutup (sudo ufw delete allow 8000)."
        else
            echo -e "  [${GREEN}OK${NC}] Port 8000 aman (tidak diekspos di UFW)."
        fi
    else
        echo -e "  [${RED}WARN${NC}] UFW Firewall NON-AKTIF! Jalankan: 'sudo ufw allow OpenSSH && sudo ufw allow \"Nginx Full\" && sudo ufw enable'"
    fi
else
    echo -e "  [${YELLOW}INFO${NC}] UFW tidak terinstal di sistem ini."
fi

echo ""

# 3. PERIKSA BINDING PORT UVICORN (Hanya 127.0.0.1)
echo -e "${YELLOW}[3/3] Memeriksa Isolasian Port 8000 (Uvicorn)...${NC}"
if ss -tulpn 2>/dev/null | grep -q "127.0.0.1:8000"; then
    echo -e "  [${GREEN}OK${NC}] Uvicorn terikat secara aman di Localhost (127.0.0.1:8000)."
elif ss -tulpn 2>/dev/null | grep -q "0.0.0.0:8000"; then
    echo -e "  [${RED}BAHAYA${NC}] Uvicorn terbuka ke seluruh LAN (0.0.0.0:8000)! Ubah host uvicorn ke 127.0.0.1."
else
    echo -e "  [${YELLOW}INFO${NC}] Layanan Uvicorn port 8000 sedang tidak berjalan."
fi

echo -e "\n${BLUE}====================================================${NC}"
echo -e "${BLUE}                    AUDIT SELESAI                   ${NC}"
echo -e "${BLUE}====================================================${NC}"