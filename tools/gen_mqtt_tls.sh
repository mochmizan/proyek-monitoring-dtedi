#!/usr/bin/env bash
# gen_mqtt_tls.sh — bikin CA + sertifikat server Mosquitto + file pin untuk firmware ESP8266.
#
# Jalankan SEKALI di Raspberry Pi (atau laptop), lalu:
#   - ca.crt, server.crt, server.key  -> /etc/mosquitto/certs/   (server.key RAHASIA, jangan di-commit)
#   - ca.crt                          -> hub/ (untuk MQTT_CA_CERT di .env)
#   - mqtt_tls_pin.h                  -> pmsr_pio/include/       (publik, aman di-commit)
#
# Pemakaian:  tools/gen_mqtt_tls.sh [OUT_DIR] [IP_PI] [IP_LAIN_OPSIONAL]
set -euo pipefail

OUT="${1:-./mqtt-certs}"
PI_IP="${2:-192.168.72.242}"      # IP Pi di AP smsb-iot (yang dipakai ESP)
EXTRA_IP="${3:-10.33.102.10}"     # IP Pi di eth0 (kampus), opsional
DAYS_CA=3650
DAYS_SRV=1825

mkdir -p "$OUT"
cd "$OUT"
umask 077

# 1) CA privat (hanya untuk menandatangani cert broker)
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS_CA" \
  -subj "/O=SMSB-IoT/CN=SMSB MQTT CA" -out ca.crt

# 2) Key + cert server broker (RSA-2048: handshake paling aman di ESP8266/BearSSL)
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/O=SMSB-IoT/CN=${PI_IP}" -out server.csr
cat > server.ext <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:${PI_IP},IP:${EXTRA_IP},IP:127.0.0.1,DNS:localhost
EOF
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$DAYS_SRV" -sha256 -extfile server.ext
rm -f server.csr server.ext ca.srl

# 3) Header pin untuk firmware: PUBLIC KEY server (bukan cert).
#    Dipin lewat setKnownKey() -> tidak butuh NTP/jam, dan tetap valid
#    kalau cert diperpanjang selama server.key yang sama dipakai.
{
  echo "#pragma once"
  echo "// AUTO-GENERATED oleh tools/gen_mqtt_tls.sh — public key broker Mosquitto (aman di-commit)."
  echo 'static const char MQTT_SERVER_PUBKEY_PEM[] PROGMEM = R"PEM('
  openssl x509 -in server.crt -pubkey -noout
  echo ')PEM";'
} > mqtt_tls_pin.h

chmod 600 ca.key server.key
chmod 644 ca.crt server.crt mqtt_tls_pin.h

echo
echo "Selesai. Verifikasi chain:"
openssl verify -CAfile ca.crt server.crt
echo
echo "Langkah berikutnya:"
echo "  sudo install -d -m 755 /etc/mosquitto/certs"
echo "  sudo install -m 644 ca.crt server.crt /etc/mosquitto/certs/"
echo "  sudo install -m 640 -o root -g mosquitto server.key /etc/mosquitto/certs/"
echo "  cp ca.crt <repo>/hub/ca.crt ;  cp mqtt_tls_pin.h <repo>/pmsr_pio/include/"
echo "  SIMPAN ca.key OFFLINE (bukan di Pi / repo)."
