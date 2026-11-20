# Spesifikasi Teknis: Raspberry Pi Knock & Approval/Decline Lifecycle
**Branch:** `feature/knock`  
**Sistem:** Proyek Monitoring Suhu & Lingkungan DTEDI SV UGM (PMSR)  
**Status:** Implemented & Verified  

---

## 1. Latar Belakang & Kebutuhan (Overview)

Berdasarkan instruksi dosen pembimbing/pengampu:
> *"Nonaktifkan fitur blocking Raspberry Pi di awal kontak, sehingga perangkat Raspberry Pi baru dapat otomatis muncul di antrean approval Dashboard Admin. Hanya ketika Administrator mengklik Decline, barulah hub dengan ID tersebut akan diblokir."*

### Masalah pada Desain Sebelumnya:
Pada arsitektur hardening sebelumnya, dependensi autentikasi `verify_hub_identity` langsung menolak permintaan dari `X-Hub-ID` yang belum terdaftar di database dengan respons `HTTP 401 Unauthorized` secara permanen. Akibatnya:
1. Hub baru tidak tersimpan di database (`hub_table`).
2. Administrator tidak dapat mengetahui bahwa ada Raspberry Pi baru yang sedang mencoba menghubungi server.
3. Dashboard `/hubs` tidak dapat menampilkan opsi persetujuan (*Approval*) karena data hub tidak pernah dibuat secara otomatis.

---

## 2. Arsitektur Solusi: Pola *Knock & Auto-Quarantine*

Untuk memenuhi instruksi tanpa mengorbankan keamanan data produksi, diimplementasikan pola **Knock & Auto-Quarantine**:

```
+-----------------------------------------------------------------------------------+
|                        SIKLUS HIDUP HUB (STATE MACHINE)                           |
+-----------------------------------------------------------------------------------+

   [ Raspberry Pi Baru Menghubungi Server ]
                     │
                     ▼
         Format X-Hub-ID Valid?
             ├── (Tidak) ──► HTTP 400 Bad Request
             └── (Ya)
                     │
                     ▼
       Cek Status di Database / Cache
         │
         ├── [ Hub Belum Terdaftar ] ──► Auto-Insert ke DB (is_active=False, status='pending_approval')
         │                                 │
         │                                 ▼
         │                         HTTP 403 Forbidden
         │                    (Karantina: Menunggu Persetujuan)
         │
         ├── [ Status: 'pending_approval' ] ──► Update last_seen (throttled) ──► HTTP 403 (Karantina)
         │
         ├── [ Status: 'blocked' (Didecline Admin) ] ──► HTTP 403 Forbidden (Akses Ditolak Permanen)
         │
         └── [ Status: 'online' / Active (Diapprove) ] ──► Verifikasi API Key ──► HTTP 200 (Telemetri Diterima)
```

### Penjelasan State:
1. **Knock Pertama Kali (Auto-Quarantine):**
   - Saat request masuk dengan `X-Hub-ID` baru, server tidak menolak mentah-mentah.
   - Server memvalidasi format ID (`^[a-zA-Z0-9_\-\.]{3,64}$`) dan kapasitas antrean pending (`MAX_PENDING_HUBS = 50`).
   - Server secara otomatis menyimpan hub ke `hub_table` dengan nilai:
     - `hub_id`: ID dari header `X-Hub-ID`.
     - `hub_name`: Sama dengan `hub_id`.
     - `hub_key`: Disimpan dari header `X-Hub-Key` (jika $\ge 16$ karakter) untuk mendukung *Zero-Touch Onboarding*.
     - `is_active`: `False` (belum diizinkan mengirim/mengambil data).
     - `status`: `"pending_approval"`.
     - `created_at` & `last_seen`: Waktu UTC saat ini.
   - Server merespons Raspberry Pi dengan status `HTTP 403 Forbidden`:  
     `"Hub terdaftar dan sedang menunggu persetujuan Admin (Pending Approval)."`

2. **Tampil di Dashboard Admin:**
   - Hub berstatus `pending_approval` langsung muncul pada halaman `/hubs` dengan indikator **Dot Oranye (Amber - Pulse)**.
   - Admin diberikan 2 tombol aksi: **[ Approve ]** dan **[ Decline ]**.

3. **Keputusan Admin (Approve vs Decline):**
   - **Jika di-Approve:**
     - Endpoint `POST /api/hubs/{hub_id}/approve` dijalankan.
     - `is_active` diubah menjadi `True`, `status` menjadi `"online"`.
     - Kredensial `hub_key` dipertahankan sehingga Raspberry Pi tidak perlu mengubah file `.env` di lapangan.
     - Cache autentikasi `hub_auth_cache` di-invalidasi.
     - Raspberry Pi langsung dapat mengirimkan telemetri (`POST /api/iot`) dan membaca antrean perintah (`GET /api/hub/commands`).
   - **Jika di-Decline:**
     - Endpoint `POST /api/hubs/{hub_id}/decline` dijalankan.
     - `is_active` disetel `False`, `status` disetel `"blocked"`.
     - Cache autentikasi di-invalidasi.
     - Seluruh permintaan lanjutan dari hub tersebut akan ditolak tegas dengan respons `HTTP 403 Forbidden`:  
       `"Akses Ditolak: Hub ini telah diblokir oleh Admin."`
   - **Unblock / Re-Approve:**
     - Jika Admin ingin membatalkan blokir, Admin cukup mengklik tombol **[ Unblock ]** di dashboard, yang akan memicu proses approve kembali.

---

## 3. Spesifikasi Kontrak API

### A. Dependensi Autentikasi Gateway: `verify_hub_identity`
* **File:** `server/app/dependencies.py`
* **Headers:** `X-Hub-ID`, `X-Hub-Key`
* **Perilaku:**
  - Hub tidak terdaftar $\rightarrow$ Auto-register ke `hub_table`, respons 403 (*Pending Approval*).
  - Hub `pending_approval` $\rightarrow$ Throttled heartbeat staging, respons 403.
  - Hub `blocked` $\rightarrow$ Respons 403 (*Diblokir oleh Admin*).
  - Hub `is_active=True` $\rightarrow$ Validasi timing-safe digest API Key, stage heartbeat, return `hub_table`.

### B. Endpoint Daftar Hub: `GET /api/hubs`
* **Akses:** Admin, Operator, Viewer (scoped by cluster) / Root (global).
* **Respons:** Menampilkan seluruh hub dengan status dinamis:
  - `"pending_approval"`: Hub baru yang mengetuk dan menunggu persetujuan.
  - `"blocked"`: Hub yang ditolak oleh admin.
  - `"online"` / `"offline"`: Hub aktif yang diawasi berdasarkan batas ambang heartbeat ($< 60$ detik).

### C. Endpoint Persetujuan: `POST /api/hubs/{hub_id}/approve`
* **Akses:** Admin / Root (memerlukan CSRF token).
* **Payload:** Kosong.
* **Respons HTTP 200:**
  ```json
  {
    "status": "approved",
    "hub_id": "hs109rs-hub-02",
    "hub_key": "0db2454beff422f2ee9a49397aa47ffd..."
  }
  ```

### D. Endpoint Penolakan: `POST /api/hubs/{hub_id}/decline` (Baru)
* **Akses:** Admin / Root (memerlukan CSRF token).
* **Payload:** Kosong.
* **Respons HTTP 200:**
  ```json
  {
    "status": "blocked",
    "hub_id": "hs109rs-hub-02"
  }
  ```

---

## 4. Perubahan Komponen Frontend Dashboard

### File yang Dimodifikasi:
1. `dashboard/src/lib/api.ts`:
   - Penambahan fungsi klien `declineHub(hubId: string)`.
2. `dashboard/src/routes/hubs.tsx`:
   - Integrasi `declineMutation` dan handler konfirmasi `handleDecline`.
   - Pembaruan `StatusDot` tone:
     - `amber` (pulse: true) untuk status `pending_approval`.
     - `red` (pulse: false) untuk status `blocked`.
     - `emerald` (pulse: true) untuk status `online`.
     - `zinc` (pulse: false) untuk status `offline`.
   - Logika tampilan tombol aksi pada `HubCard`:
     - **Pending Approval:** Menampilkan tombol hijau `Approve` dan tombol merah `Decline`.
     - **Blocked:** Menampilkan tombol `Unblock` untuk memulihkan akses jika diperlukan.
     - **Active:** Menampilkan tombol `Revoke` untuk mencabut akses hub yang sedang beroperasi.

---

## 5. Mekanisme Proteksi & Keamanan (Defense-in-Depth)

Meskipun sistem mengizinkan pendaftaran awal secara otomatis, terdapat proteksi lapang berlapis:
1. **RegEx Validation:** ID hub harus memenuhi `^[a-zA-Z0-9_\-\.]{3,64}$`. Karakter berbahaya (SQL injection, path traversal) langsung ditolak dengan `HTTP 400 Bad Request`.
2. **Queue Cap (Anti-DoS):** Batas maksimal hub berstatus `pending_approval` dalam database dibatasi maksimal 50 hub. Jika melebihi, server merespons `HTTP 429 Too Many Requests`.
3. **Data Quarantine:** Hub berstatus `pending_approval` **sama sekali tidak dapat**:
   - Menulis telemetri sensor ke tabel data (`/api/iot` menolak dengan 403).
   - Membaca perintah kontrol aktuator (`/api/hub/commands` menolak dengan 403).
   - Mengubah status perangkat di database.
4. **Audit Logging:** Setiap aksi `Approve` dan `Decline` oleh Administrator dicatat secara persisten ke dalam tabel audit log `UserAuditLog`.

---

## 6. Ringkasan Pengujian Otomatis

Seluruh alur fitur telah diuji melalui unit & integration test pada file:
`server/test_hub_knock_lifecycle.py`

| No | Kasus Uji | Skenario | Hasil |
| :--- | :--- | :--- | :--- |
| 1 | `test_unknown_hub_knock_auto_registration` | Hub asing melakukan request pertama kali | **PASSED (100%)** |
| 2 | `test_pending_hub_stays_quarantined` | Hub pending mengirim request berulang | **PASSED (100%)** |
| 3 | `test_dashboard_lists_pending_hub` | Dashboard membaca hub pending approval | **PASSED (100%)** |
| 4 | `test_admin_approve_hub` | Admin menyetujui hub & hub mulai stream telemetri | **PASSED (100%)** |
| 5 | `test_cannot_approve_already_active_hub` | Pencegahan re-approve hub aktif (409) | **PASSED (100%)** |
| 6 | `test_admin_decline_and_block_hub` | Admin menolak hub & verifikasi blokir permanen | **PASSED (100%)** |
| 7 | `test_operator_cannot_approve_or_decline` | Verifikasi RBAC (Operator dilarang approve/decline) | **PASSED (100%)** |
| 8 | `test_admin_can_unblock_previously_declined_hub` | Admin memulihkan hub yang sebelumnya diblokir | **PASSED (100%)** |
| 9 | `test_malformed_hub_id_rejected` | ID hub tidak valid ditolak dengan HTTP 400 | **PASSED (100%)** |

**Total:** 9 Passed, 0 Failed, 0 Regressions.
