======================================================================
         HUBGATE v5 - SECURE API & EDGE GATEWAY (HTTPS & AUTH)
======================================================================

HubGate v5 adalah sistem ingestion data IoT enterprise berbasis FastAPI, 
Pydantic, dan SQLAlchemy PostgreSQL. Versi 5 berfokus pada Security Hardening 
menggunakan arsitektur pertahanan berlapis (Defense-in-Depth):
1. Enkripsi Transport (Nginx Reverse Proxy + HTTPS SSL/TLS).
2. Autentikasi Hub Berbasis Database (Verifikasi Header X-Hub-ID & X-Hub-Key).
3. Proteksi Endpoint Admin menggunakan HTTP Basic Auth.
4. Anti Brute-Force & Spam Request menggunakan Rate Limiting (slowapi).
5. Isolasi Whitelist Per-Hub (Setiap Edge Hub hanya mengakses datanya sendiri).

----------------------------------------------------------------------
1. PRASYARAT SISTEM (PREREQUISITES)
----------------------------------------------------------------------
- Python 3.10 atau lebih baru
- PostgreSQL Server (Database Utama)
- Nginx Web Server (Reverse Proxy & HTTPS Termination)
- OpenSSL (Pembuat Sertifikat SSL/TLS)
- Mosquitto MQTT Broker (Berjalan di Raspberry Pi / Edge Hub)
- Linux / Ubuntu Server Environment (UFW Firewall Aktif)

----------------------------------------------------------------------
2. STRUKTUR BERKAS PROYEK
----------------------------------------------------------------------
v5/
├── hubgatev5.py        # Main Gateway, Rate Limiting & Auth Dependencies
├── schemasv5.py        # Skema Validasi Pydantic & Discriminated Unions
├── databasev5.py       # Konfigurasi SQLAlchemy Engine, Session & get_db()
├── modelsv5.py         # Skema ORM Database (hubs, dev_table, data_table)
├── init_sqlv5.py       # Skrip Inisialisasi Tabel & Auto-Seeding Hub Utama
├── run_hubgatev5.sh    # Skrip Otomasi Deployment Bash (SSL + Nginx + Uvicorn)
├── check_security_v5.sh # Skrip Audit Keamanan Lokal (UFW & File Permission)
├── cert.crt            # [AUTO-GEN] Sertifikat SSL/TLS HTTPS
├── cert.key            # [AUTO-GEN] Kunci Privat SSL/TLS (chmod 600)
├── requirements.txt    # Dependensi Library Python (Termasuk slowapi)
├── .env                # Variabel Konfigurasi & Kredensial Sensitif (chmod 600)
└── README.txt           # Dokumentasi Sistem Ini

----------------------------------------------------------------------
3. KONFIGURASI ENVIRONMENT (.env)
----------------------------------------------------------------------
Pastikan file `.env` sudah dibuat di direktori utama sebelum menjalankan 
aplikasi. Setel izin file menjadi `chmod 600 .env` di Linux.

# Kredensial Admin Server (Basic Auth)
SERVER_USER=caslie
PASSWORD_USER=caslie_admin_v5_sec123!

# Database PostgreSQL
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hubgate_v5_db

# Identitas Default Hub Pertama
HUB_NAME=RASPI_HUB_01
HUB_KEY=rahasia_hub_01_xyz

----------------------------------------------------------------------
4. CARA MENJALANKAN SERVER (NGINX + UVICORN)
----------------------------------------------------------------------

[METODE 1: Menggunakan Skrip Otomatis Bash (Sangat Direkomendasikan)]
--------------------------------------------------------------------
1. Beri izin eksekusi pada skrip:
   $ chmod +x run_hubgatev5.sh check_security_v5.sh

2. Jalankan skrip dengan akses sudo:
   $ sudo ./run_hubgatev5.sh

*Skrip ini secara otomatis akan:*
 1. Membuat sertifikat SSL/TLS Self-Signed (cert.crt & cert.key).
 2. Menulis & mengaktifkan konfigurasi Nginx Reverse Proxy di port 443.
 3. Menyiapkan venv, menginstal dependensi, dan menginisialisasi tabel DB V5.
 4. Menjalankan Uvicorn secara terisolasi di localhost (127.0.0.1:8000).


[METODE 2: Menjalankan di Background Service Production (systemd)]
-------------------------------------------------------------------
1. Buat file service systemd di Linux:
   $ sudo nano /etc/systemd/system/hubgate.service

2. Isi dengan konfigurasi berikut (sesuaikan path):
   [Unit]
   Description=HubGate v5 Secure Gateway Service
   After=network.target postgresql.service nginx.service

   [Service]
   User=caslie
   WorkingDirectory=/home/caslie/SMRS/backend/v5
   ExecStart=/home/caslie/SMRS/backend/v5/venv/bin/uvicorn hubgatev5:api --host 127.0.0.1 --port 8000 --workers 4
   Restart=always
   RestartSec=5
   EnvironmentFile=/home/caslie/SMRS/backend/v5/.env

   [Install]
   WantedBy=multi-user.target

3. Reload dan jalankan service:
   $ sudo systemctl daemon-reload
   $ sudo systemctl start hubgate
   $ sudo systemctl enable hubgate

----------------------------------------------------------------------
5. AUDIT KEAMANAN LOKAL (SECURITY CHECK)
----------------------------------------------------------------------
Jalankan skrip audit keamanan untuk memastikan UFW firewall, port binding, 
dan izin berkas sensitif sudah dikunci rapat:

   $ ./check_security_v5.sh

----------------------------------------------------------------------
6. MENAMBAHKAN JENIS PERANGKAT IOT BARU
----------------------------------------------------------------------
Untuk menambahkan jenis sensor/alat IoT baru di `schemasv5.py`:

1. Buka `schemasv5.py`.
2. Buat class Pydantic baru:
   class PumpData(IotDataBase):
       DEV_TYPE: Literal["PUMP"]
       PRESSURE: float

3. Daftarkan class tersebut ke dalam `IotPayload`:
   IotPayload = Annotated[
       Union[ATSData, TSData, ACCData, PumpData], 
       Field(discriminator="DEV_TYPE")
   ]

----------------------------------------------------------------------
7. DOKUMENTASI ENDPOINT API (V5)
----------------------------------------------------------------------
Akses Swagger UI interaktif terenkripsi di browser: 
https://<IP_SERVER>/docs  (Port 443 HTTPS)

======================================================================
A. ENDPOINT ADMIN (Dilindungi HTTP Basic Auth)
======================================================================
- POST /api/admin/hubs
  Fungsi: Mendaftarkan Hub (Raspberry Pi) resmi baru ke database.
  Rate Limit: 10 req/menit.

- POST /api/devices/{id}/approve
  Fungsi: Menyetujui perangkat IoT yang pending agar statusnya aktif.
  Rate Limit: 30 req/menit.

======================================================================
B. ENDPOINT HUB / EDGE (Dilindungi Header X-Hub-ID & X-Hub-Key)
======================================================================
- GET /api/devices
  Fungsi: Synchronize whitelist perangkat aktif (Khusus untuk Hub terkait).
  Rate Limit: 30 req/menit.

- POST /api/iot
  Fungsi: Meneruskan data telemetri terverifikasi dari Edge Hub.
  Rate Limit: 120 req/menit.

- POST /api/iot/unapproved
  Fungsi: Menerima laporan MAC Address asing yang diblokir di Edge Hub.
  Rate Limit: 60 req/menit.
======================================================================