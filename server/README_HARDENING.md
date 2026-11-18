# Hardening Keamanan PMSR

Dokumen ini merangkum pekerjaan hardening pada backend PMSR (FastAPI) sebagai
respons atas 18 temuan **Laporan Penetration Test PMSR** (target VPS
`10.33.102.141`, tanggal uji 4 November 2026).

> **Catatan lingkup.** Snapshot kode ini (13 Oktober 2026) lebih baru daripada
> versi yang berjalan di VPS saat pengujian. Akibatnya sebagian temuan tidak
> berlaku 1:1 pada kode ini (mis. tidak ada model *cluster* dan tidak ada
> endpoint hapus-user). Hal tersebut dijelaskan secara transparan, bukan
> ditutupi. Lihat `LAPORAN_HARDENING_PMSR.pdf` untuk detail lengkap.

---

## Ringkasan status 18 temuan

| ID | Sev | Temuan | Status | Jenis |
|----|-----|--------|--------|-------|
| F-01 | HIGH | BOLA/IDOR read resource | Didokumentasikan (N/A: tak ada cluster) | Kode |
| F-02 | HIGH | Cross-cluster device command | Dikendalikan (RBAC) | Kode |
| F-03 | HIGH | `.env` world-readable + rahasia bocor | Skrip infra | Infra |
| F-04 | HIGH | Tanpa rate limit IoT | **Diperbaiki** | Kode |
| F-05 | MED | Tanpa body-size limit | **Diperbaiki** | Kode |
| F-06 | MED | Future timestamp diterima | **Diperbaiki** | Kode |
| F-07 | MED | Cross-device telemetry injection | Sudah aman (verifikasi) | Kode |
| F-08 | MED | Vite dev server terekspos | Skrip infra | Infra |
| F-09 | MED | SSH password auth aktif | Skrip infra | Infra |
| F-10 | MED | Kredensial lemah/default | Skrip infra (manual) | Infra |
| F-11 | MED | GitHub PAT di filesystem | Skrip infra | Infra |
| F-12 | LOW | Error handling DELETE user 500 | N/A di versi ini | Kode |
| F-13 | LOW | Security headers minim | **Diperbaiki** | Kode |
| F-14 | LOW | Dokumentasi API terekspos | **Diperbaiki** | Kode |
| F-15 | LOW | 71 paket OS belum update | Skrip infra | Infra |
| F-16 | LOW | Secure flag cookie dari header client | **Diperbaiki** | Kode |
| F-17 | LOW | Command replay/duplicate | **Diperbaiki** | Kode |
| F-18 | INFO | Tailscale ACL perlu ditinjau | Skrip infra (manual) | Infra |

---

## Perubahan kode (level aplikasi)

| Berkas | Perubahan | Temuan |
|--------|-----------|--------|
| `app/core/config.py` | Konstanta hardening + helper env (`MAX_BODY_SIZE`, `MAX_FUTURE_TIMESTAMP_SECONDS`, `ENABLE_DOCS`, `COOKIE_SECURE`, `ENABLE_HSTS`, batas rate per-hub) | F-05/06/14/16/13/04 |
| `app/core/rate_limit.py` | `get_hub_rate_key()` — rate-limit per `X-Hub-ID` | F-04 |
| `app/core/security_middleware.py` *(baru)* | `BodySizeLimitMiddleware` (413) + `SecurityHeadersMiddleware` | F-05, F-13 |
| `app/main.py` | Registrasi middleware + guard docs/redoc/openapi | F-05/13/14 |
| `app/routers/iot.py` | Tolak timestamp masa depan (422) + rate limit per-hub | F-06, F-04 |
| `app/routers/commands.py` | Idempotency perintah via header `Idempotency-Key` | F-17 |
| `app/routers/auth.py`, `auth.py` | Flag `Secure` cookie dari `COOKIE_SECURE` | F-16 |

### Variabel lingkungan baru (opsional, punya default aman)

```bash
ENV=prod                         # mengaktifkan mode produksi
ENABLE_DOCS=false                # default: nonaktif saat ENV=prod (F-14)
COOKIE_SECURE=true               # default: aktif saat ENV=prod (F-16)
ENABLE_HSTS=true                 # default: aktif saat ENV=prod (F-13)
MAX_BODY_SIZE=1048576            # batas body JSON dalam byte, default 1 MB (F-05)
MAX_FUTURE_TIMESTAMP_SECONDS=300 # toleransi clock-skew telemetri, default 5 mnt (F-06)
IOT_RATE_LIMIT_PER_HUB=1200/minute
IOT_BATCH_RATE_LIMIT_PER_HUB=60/minute
```

---

## Hardening infrastruktur — `harden_infra.sh`

Skrip ini dijalankan **oleh Anda di VPS** (bukan oleh agen). Aman secara default:

- **Dry-run** sebagai default (tidak mengubah apa pun).
- Perlu `--apply` untuk menerapkan perubahan otomatis.
- Membuat cadangan `<file>.bak.<timestamp>` sebelum mengubah.
- **Tidak** me-restart sshd atau reboot otomatis.
- Memeriksa `~/.ssh/authorized_keys` sebelum mematikan password-auth (anti lockout).

```bash
# Di VPS, sebagai user alfido:
./harden_infra.sh            # 1) tinjau (tidak mengubah apa pun)
./harden_infra.sh --apply    # 2) terapkan langkah otomatis yang aman

# 3) kerjakan item "ACTION REQUIRED (manual)":
#    - rotasi HUB_KEY / CSRF_SECRET / password DB  (sudah bocor di laporan!)
#    - ganti password OS & seed user aplikasi
#    - revoke GitHub PAT
#    - sudo systemctl restart ssh   (setelah login key terkonfirmasi)
#    - sudo ufw enable
```

Mencakup: F-03 (chmod 600 `.env`), F-08 (bind Vite/build + ufw), F-09 (SSH
key-only), F-10 (kredensial — manual), F-11 (rename folder PAT), F-15 (apt
upgrade + unattended-upgrades), F-18 (tinjau ACL Tailscale), plus firewall ufw.

---

## Verifikasi & pengujian

Test suite dijalankan **per-berkas** (harness berbagi satu SQLite, reset DB di
antara berkas) agar hasil deterministik.

| Skenario | Hasil |
|----------|-------|
| Baseline (kode asli) | 254 lulus, 4 gagal |
| Setelah patch (tanpa test baru) | 254 lulus, 4 gagal — **identik, 0 regresi** |
| Setelah patch + test hardening | 263 lulus, 4 gagal |
| Test hardening baru (`test_hardening_pentest.py`) | 9 lulus |

4 kegagalan pra-ada bersifat lingkungan (modul `requests` tak terpasang;
migrasi Alembic/partisi yang menyasar PostgreSQL) — identik di kode asli, bukan
akibat hardening.

### Cara menjalankan test

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest httpx

# jalankan per-berkas (disarankan — harness berbagi SQLite)
for f in test_*.py; do rm -f hubgatev5.db test_hardening.db; pytest -q "$f"; done

# hanya test hardening
pytest -q test_hardening_pentest.py
```

---

## Dokumentasi PDF

`LAPORAN_HARDENING_PMSR.pdf` (7 halaman A4) memuat cover, tabel status 18
temuan, detail per-temuan dengan before/after, tabel skrip infra, hasil
verifikasi, dan daftar berkas yang diubah.

Regenerasi PDF:

```bash
python3 generate_hardening_doc.py   # butuh reportlab
```

Salinan PDF tersedia di:
- `../../LAPORAN_HARDENING_PMSR.pdf` (folder `pmld/`)
- `./LAPORAN_HARDENING_PMSR.pdf` (folder `server/`)
