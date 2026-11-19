# MQTT over TLS (ESP8266 ⇄ Mosquitto Pi ⇄ HubBrain)

Sebelumnya: ESP → `:1883` plaintext (username/password MQTT + data terbaca siapa pun di Wi-Fi `smsb-iot`).
Sekarang: ESP → `:8883` TLS 1.2. Firmware mem-pin public key broker, jadi broker palsu ditolak.
Tidak butuh NTP/jam (Pi tanpa RTC & internet).

```
ESP8266 (TS/ATS/AC) --TLS 8883--> Mosquitto (Pi) --loopback 1883--> hub/main.py --HTTPS--> server
```

## 1. Di Raspberry Pi (sekali saja)

```bash
tools/gen_mqtt_tls.sh ./mqtt-certs 192.168.72.242 10.33.102.10
sudo install -d -m 755 /etc/mosquitto/certs
sudo install -m 644 mqtt-certs/ca.crt mqtt-certs/server.crt /etc/mosquitto/certs/
sudo install -m 640 -o root -g mosquitto mqtt-certs/server.key /etc/mosquitto/certs/
sudo cp mosquitto/config/mosquitto.tls.conf /etc/mosquitto/conf.d/tls.conf
# pastikan /etc/mosquitto/mosquitto.conf tidak punya "listener 1883" sendiri
sudo systemctl restart mosquitto && sudo systemctl status mosquitto
```

Simpan `ca.key` offline (flashdisk), jangan di Pi/repo. `server.key` jangan di-commit.

Tes dari Pi:
```bash
mosquitto_sub -h 192.168.72.242 -p 8883 --cafile mqtt-certs/ca.crt -u hubadmin -P '<pass>' -t 'hs109rs/#' -v
# tanpa --cafile / port 1883 dari luar harus gagal
```

## 2. hub/main.py
Default tetap `localhost:1883` (loopback, tidak lewat jaringan) → tidak perlu ubah `.env`.
Kalau mau TLS juga di sisi hub: `cp mqtt-certs/ca.crt hub/ca.crt`, lalu di `hub/.env`:
```
MQTT_TLS=true
MQTT_PORT=8883
MQTT_HOST=127.0.0.1      # ada di SAN sertifikat
MQTT_CA_CERT=/home/<user>/hub/ca.crt
```
`sudo systemctl restart hubbrain`. Log harus muncul `[SECURITY] MQTT TLS aktif`.

## 3. Firmware (pmsr_pio)
```bash
cp mqtt-certs/mqtt_tls_pin.h pmsr_pio/include/      # publik, aman di-commit
cd pmsr_pio
pio run -e wemos_ts  -t upload
pio run -e wemos_ats -t upload
pio run -e wemos_ac  -t upload
```
Cek TS/AC lewat serial monitor (115200): harus `[MQTT] connected`; `failed rc=-2` = TLS/pin gagal
(pin tidak cocok dengan server.key broker, atau port/IP salah). Node ATS memakai Serial untuk UART ke
Pro Mini, jadi cek lewat log Mosquitto / `journalctl -u hubbrain` (`[POST SUCCESS] ... ATS`).

Urutan rilis: restart Mosquitto dengan 8883 aktif DULU, baru flash node satu per satu
(node lama yang belum di-flash tetap tidak bisa konek karena 1883 sudah loopback-only).

## 4. Catatan
- Node ini **ESP8266 (Wemos D1 Mini)**, bukan ESP32 — kode memakai `BearSSL::WiFiClientSecure` (ESP8266). Kalau nanti pindah ke ESP32, ganti jadi `WiFiClientSecure` + `setCACert()`.
- Handshake TLS di ESP8266 ~1–3 dtk dan memakai ±20–25 KB heap. Sudah dihemat (`setBufferSizes(1024,512)`), tapi cek `ESP.getFreeHeap()` di node AC (paling banyak library) setelah flash.
- Jalur UART Pro Mini ⇄ Wemos ATS tetap plaintext (kabel lokal dalam panel).
- Ini enkripsi transport (ESP→broker), bukan end-to-end ke server; di Pi data tetap terbaca sebelum di-forward lewat HTTPS.
- Cert broker berlaku 5 tahun. Perpanjang dengan `server.key` yang sama → pin di firmware tetap valid.
- SSH tunnel di `hub/AGENTS.md` (`-L 1883:10.33.102.10:1883`) tidak jalan lagi karena 1883 hanya loopback; ganti ke `-L 8883:10.33.102.10:8883` dan pakai `--cafile`.
- Jika sertifikat/key bocor atau diganti dengan key baru: generate ulang, copy `mqtt_tls_pin.h`, flash ulang semua node.
