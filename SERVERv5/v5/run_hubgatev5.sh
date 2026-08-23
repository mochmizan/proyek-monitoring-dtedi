#!/bin/bash
set -euo pipefail

# Warna Terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}    Deploy & Start HubGate v5 + Nginx    ${NC}"
echo -e "${GREEN}=========================================${NC}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
FRONTEND_DIR="$REPO_ROOT/clients/gui-app"
cd "$SCRIPT_DIR"

# 1. DETEKSI IP SERVER
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
if [ -z "$SERVER_IP" ]; then
    SERVER_IP="192.168.72.245"
fi

NGINX_CONF="/etc/nginx/sites-available/hubgate"
CERT_KEY="$SCRIPT_DIR/cert.key"
CERT_CRT="$SCRIPT_DIR/cert.crt"

# 2. BUILD FRONTEND JIKA BELUM ADA DIST
if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    echo -e "${YELLOW}[FRONTEND] Building React GUI SPA at $FRONTEND_DIR...${NC}"
    if [ -d "$FRONTEND_DIR" ]; then
        (cd "$FRONTEND_DIR" && npm run build)
    fi
fi

# 3. BUAT SERTIFIKAT SSL JIKA BELUM ADA
if [ ! -f "$CERT_KEY" ] || [ ! -f "$CERT_CRT" ]; then
    echo -e "${YELLOW}[SSL] Membuat sertifikat SSL Self-Signed baru untuk $SERVER_IP...${NC}"
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout "$CERT_KEY" \
      -out "$CERT_CRT" \
      -subj "/CN=$SERVER_IP" \
      -addext "subjectAltName=IP:$SERVER_IP,DNS:localhost"
fi

# 4. GENERATE KONFIGURASI NGINX SAME-ORIGIN OTOMATIS
if [ -d "/etc/nginx" ]; then
    echo -e "${YELLOW}[NGINX] Memperbarui /etc/nginx/sites-available/hubgate (server_name: $SERVER_IP)...${NC}"

    sudo bash -c "cat << 'EOF' > $NGINX_CONF
server {
    listen 80;
    server_name SERVER_IP_VAL _;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name SERVER_IP_VAL _;

    ssl_certificate     CERT_CRT_VAL;
    ssl_certificate_key CERT_KEY_VAL;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    # API Reverse Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \"upgrade\";
    }

    # Static Floor Plan & Asset Uploads
    location /static/ {
        alias STATIC_DIR_VAL/;
        expires 30d;
        try_files \$uri @api_backend;
    }

    location @api_backend {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Frontend SPA Static Assets
    location ~* ^/assets/(.+\\.(?:js|css|png|jpg|jpeg|gif|svg|ico|webp|woff2?))$ {
        root FRONTEND_DIST_VAL;
        expires 1y;
        add_header Cache-Control \"public, max-age=31536000, immutable\";
    }

    # Frontend SPA Entrypoint
    location / {
        root FRONTEND_DIST_VAL;
        try_files \$uri \$uri/ /index.html;
    }
}
EOF"

    # Inject nilai variabel ke file konfigurasi
    sudo sed -i "s|SERVER_IP_VAL|$SERVER_IP|g" $NGINX_CONF
    sudo sed -i "s|CERT_CRT_VAL|$CERT_CRT|g" $NGINX_CONF
    sudo sed -i "s|CERT_KEY_VAL|$CERT_KEY|g" $NGINX_CONF
    sudo sed -i "s|STATIC_DIR_VAL|$SCRIPT_DIR/static|g" $NGINX_CONF
    sudo sed -i "s|FRONTEND_DIST_VAL|$FRONTEND_DIR/dist|g" $NGINX_CONF

    # Symlink ke sites-enabled
    if [ ! -f /etc/nginx/sites-enabled/hubgate ]; then
        sudo ln -s /etc/nginx/sites-available/hubgate /etc/nginx/sites-enabled/
    fi

    # Test dan reload Nginx
    echo -e "${YELLOW}[NGINX] Memeriksa sintaks dan merefresh Nginx...${NC}"
    sudo nginx -t
    sudo systemctl reload nginx
fi

# 5. SETUP VIRTUAL ENVIRONMENT & DEPENDENCIES
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet

# 6. INISIALISASI DATABASE (ADDITIVE MIGRATIONS)
python init_sqlv5.py

# 7. JALANKAN UVICORN
HOST="127.0.0.1"
PORT="8000"
WORKERS=4

echo -e "${GREEN}[SERVER] HubGate V5 aktif di https://$SERVER_IP via Nginx Same-Origin Proxy${NC}"
uvicorn hubgatev5:api --host "$HOST" --port "$PORT" --workers "$WORKERS"

