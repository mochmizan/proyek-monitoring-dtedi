======================================================================
                HUBBRAIN V5 - EDGE IOT GATEWAY
======================================================================

HubBrain V5 adalah layanan Edge Gateway berbasis Python yang berjalan di 
Raspberry Pi 4. Berfungsi sebagai "satpam" lokal yang menyaring data dari 
node-node IoT via MQTT, melakukan pemfilteran whitelist (anti-DDoS), 
mengirimkan konfigurasi balik ke IoT, dan meneruskan telemetri bersih ke 
Cloud Server (HubGate V5) melalui jalur terenkripsi HTTPS (SSL/TLS).

Pada versi 5, sistem ditingkatkan dengan 3 fitur keamanan utama (Security Hardening):
1. Authenticated Upstream: Mengirimkan Header X-Hub-ID dan X-Hub-Key ke Server V5.
2. Strict SSL Verification: Memverifikasi keabsahan HTTPS server menggunakan cert.crt.
3. Authenticated Local MQTT: Broker Mosquitto dikunci dengan username & password.

----------------------------------------------------------------------
1. FITUR UTAMA
----------------------------------------------------------------------
- Edge Filtering (Anti-DDoS): Memblokir trafik dari MAC Address asing di 
  tingkat RAM Raspberry Pi tanpa membebani server utama.
- Authenticated Synchronized Whitelist: Otomatis mengunduh daftar perangkat 
  resmi dari Server via HTTPS dengan verifikasi X-Hub-Key.
- Pending Device Alert: Melaporkan perangkat baru (MAC asing) ke server 
  agar muncul di Dashboard Admin untuk proses approval.
- Downlink Configuration: Mengirim instruksi/konfigurasi balik ke node 
  IoT resmi melalui MQTT topic spesifik.
- Strict Secure Upstream (HTTPS): Komunikasi terenkripsi penuh & terverifikasi 
  sertifikat SSL lokal (cert.crt) untuk mencegah serangan Man-in-the-Middle.

----------------------------------------------------------------------
2. PRASYARAT SISTEM (PREREQUISITES)
----------------------------------------------------------------------
- Perangkat Keras: Raspberry Pi 4 (Raspberry Pi OS / Linux)
- Python 3.10 atau lebih baru
- Broker MQTT lokal (Mosquitto MQTT) dengan autentikasi aktif
- Sertifikat SSL Server (`cert.crt`) tersimpan di folder proyek
- Koneksi jaringan ke Node IoT (Wi-Fi/LAN) dan Cloud Server (HTTPS/LAN)

----------------------------------------------------------------------
3. STRUKTUR BERKAS
----------------------------------------------------------------------
hubbrain/
├── brain_of_hub_v5.py   # Skrip Utama Edge Filtering Hub V5
├── cert.crt            # [WAJIB] Sertifikat SSL Self-Signed dari Server HubGate
├── requirements.txt     # Dependensi Python untuk Hub
├── .env                 # Konfigurasi MQTT Auth & Credentials Server V5
└── README.txt           # Dokumentasi ini

----------------------------------------------------------------------
4. KONFIGURASI ENVIRONMENT (.env)
----------------------------------------------------------------------
Buat file `.env` di direktori yang sama dengan `brain_of_hub_v5.py`:

# Konfigurasi MQTT Lokal (Dengan Autentikasi)
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=hub_user
MQTT_PASS=password_rahasia_mosquitto
MQTT_TOPIC=hs109rs/#

# Identitas & Kredensial Hub
HUB_NAME=RASPI_HUB_01
HUB_KEY=rahasia_hub_01_xyz

# URL Endpoint Cloud Server HTTPS (HubGate V5 via Nginx Port 443)
SERVER_URL=https://10.33.203.3/api/iot
SERVER_DEVICES_URL=https://10.33.203.3/api/devices
SERVER_ALERT_URL=https://10.33.203.3/api/iot/unapproved

----------------------------------------------------------------------
5. CARA INSTALASI & MENJALANKAN
----------------------------------------------------------------------

[Langkah 1: Install & Konfigurasi Autentikasi Mosquitto Broker]
----------------------------------------------------------------
1. Install Mosquitto:
   $ sudo apt update
   $ sudo apt install mosquitto mosquitto-clients -y

2. Buat akun username & password untuk Mosquitto:
   $ sudo mosquitto_passwd -c /etc/mosquitto/passwd hub_user

3. Konfigurasi Mosquitto agar menolak akses tanpa password:
   $ sudo bash -c 'cat <<EOF > /etc/mosquitto/conf.d/default.conf
allow_anonymous false
password_file /etc/mosquitto/passwd
listener 1883
EOF'

4. Enable & Restart Service:
   $ sudo systemctl enable mosquitto
   $ sudo systemctl restart mosquitto


[Langkah 2: Setup Environment Python]
-------------------------------------
1. Masuk ke direktori proyek:
   $ cd /home/pi/hubbrain

2. Buat dan aktifkan Virtual Environment:
   $ python3 -m venv venv
   $ source venv/bin/activate

3. Install dependensi:
   $ pip install -r requirements.txt
   
   *(Isi requirements.txt: paho-mqtt, requests, python-dotenv)*


[Langkah 3: Salin Sertifikat SSL dari Server HubGate]
----------------------------------------------------
Salin file `cert.crt` dari server utama ke folder `/home/pi/hubbrain/`:
   $ scp user@10.33.203.3:/path/to/server/cert.crt /home/pi/hubbrain/


[Langkah 4: Jalankan Manual (Development)]
------------------------------------------
$ python brain_of_hub_v5.py


[Langkah 5: Jalankan Otomatis di Background (Production Service)]
-----------------------------------------------------------------
Agar HubBrain V5 otomatis menyala saat Raspberry Pi booting:

1. Buat file service systemd:
   $ sudo nano /etc/systemd/system/hubbrain.service

2. Masukkan konfigurasi berikut:
   [Unit]
   Description=HubBrain V5 Edge IoT Gateway Service
   After=network.target mosquitto.service

   [Service]
   User=pi
   WorkingDirectory=/home/pi/hubbrain
   ExecStart=/home/pi/hubbrain/venv/bin/python brain_of_hub_v5.py
   Restart=always
   RestartSec=5
   EnvironmentFile=/home/pi/hubbrain/.env

   [Install]
   WantedBy=multi-user.target

3. Aktifkan service:
   $ sudo systemctl daemon-reload
   $ sudo systemctl start hubbrain
   $ sudo systemctl enable hubbrain

4. Cek status & log layanan:
   $ sudo systemctl status hubbrain
   $ journalctl -u hubbrain -f

----------------------------------------------------------------------
6. TOPIC MQTT YANG DIGUNAKAN
----------------------------------------------------------------------
- Subscribe (Uplink dari IoT):
  `hs109rs/#`            : Menerima JSON telemetri dari semua perangkat IoT.

- Publish (Downlink ke IoT):
  `iot/config/{DEV_ID}`   : Mengirim konfirmasi & konfigurasi balik ke 
                            MAC Address terdaftar.
======================================================================