#!/usr/bin/env python3
# generate_hardening_doc.py — build the PMSR hardening report PDF with ReportLab.
import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    HRFlowable,
)

OUTPUT = "LAPORAN_HARDENING_PMSR.pdf"

# --- Palette ---
NAVY = colors.HexColor("#0f2a4a")
BLUE = colors.HexColor("#1f5aa6")
GREY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#eef3f8")
GREEN = colors.HexColor("#1b7a3d")
AMBER = colors.HexColor("#9a6b00")
RED = colors.HexColor("#b00020")

styles = getSampleStyleSheet()

def S(name, **kw):
    styles.add(ParagraphStyle(name=name, **kw))

S("TitleBig", parent=styles["Title"], fontSize=24, textColor=NAVY, spaceAfter=6, leading=28)
S("SubTitle", parent=styles["Normal"], fontSize=12, textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
S("H1", parent=styles["Heading1"], fontSize=16, textColor=NAVY, spaceBefore=14, spaceAfter=6)
S("H2", parent=styles["Heading2"], fontSize=13, textColor=BLUE, spaceBefore=10, spaceAfter=4)
S("Body", parent=styles["Normal"], fontSize=10, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
S("Small", parent=styles["Normal"], fontSize=8.5, leading=12, textColor=GREY)
S("CodeBox", parent=styles["Code"], fontSize=8, leading=11, backColor=LIGHT,
  borderPadding=6, textColor=colors.HexColor("#1a1a1a"), spaceBefore=3, spaceAfter=6)
S("Cell", parent=styles["Normal"], fontSize=8.5, leading=11)
S("CellB", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.white)

story = []

def p(txt, s="Body"):
    story.append(Paragraph(txt, styles[s]))

def sp(h=6):
    story.append(Spacer(1, h))

def rule():
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cfd8e3"),
                            spaceBefore=4, spaceAfter=8))

def code(txt):
    safe = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br/>")
    story.append(Paragraph(safe, styles["CodeBox"]))

# ---------------------------------------------------------------------------
# COVER
# ---------------------------------------------------------------------------
sp(60)
p("LAPORAN HARDENING KEAMANAN", "TitleBig")
p("Sistem PMSR (Proyek Monitoring DTEDI)", "SubTitle")
p("Remediasi atas 18 Temuan Penetration Test", "SubTitle")
sp(18)

cover_tbl = Table([
    ["Target", "VPS 10.33.102.141 (ubuntu-alfido)"],
    ["Stack", "FastAPI (uvicorn), React/Vite, PostgreSQL 16, Tailscale, Docker"],
    ["Basis Temuan", "Laporan Pentest PMSR — 4 November 2026 (4 HIGH, 7 MED, 6 LOW, 1 INFO)"],
    ["Lingkup Dokumen", "Remediasi kode aplikasi (backend) + skrip hardening infrastruktur"],
    ["Tanggal Hardening", datetime.date.today().strftime("%d %B %Y")],
], colWidths=[38*mm, 120*mm])
cover_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), NAVY),
    ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("BACKGROUND", (1, 0), (1, -1), LIGHT),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
]))
story.append(cover_tbl)
sp(20)
p("Dokumen ini menjelaskan tindakan hardening yang diterapkan pada basis kode PMSR "
  "sebagai respons atas laporan penetration test. Untuk setiap temuan dicantumkan: ringkasan "
  "risiko, akar masalah, tindakan perbaikan, berkas yang diubah, dan hasil verifikasi.", "Body")
sp(10)
note = Table([[Paragraph(
    "<b>Catatan lingkup penting.</b> Salinan kode sumber yang di-hardening (snapshot repositori, "
    "13 Oktober 2026) ternyata merupakan versi yang lebih baru daripada yang berjalan di VPS saat "
    "pengujian (4 November 2026). Akibatnya beberapa temuan sudah tidak berlaku 1:1 pada kode ini "
    "(mis. tidak ada model <i>cluster</i> dan tidak ada endpoint hapus-user). Hal tersebut dijelaskan "
    "secara transparan per-temuan, bukan ditutupi.", styles["Cell"])]],
    colWidths=[158*mm])
note.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff6e5")),
    ("BOX", (0, 0), (-1, -1), 0.8, AMBER),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(note)
story.append(PageBreak())

# ---------------------------------------------------------------------------
# RINGKASAN STATUS
# ---------------------------------------------------------------------------
p("1. Ringkasan Status Remediasi", "H1")
rule()

def badge(txt, color):
    return Paragraph(f'<font color="white"><b>{txt}</b></font>', styles["Cell"]), color

status_rows = [
    ["ID", "Severitas", "Temuan", "Status", "Jenis"],
    ["F-01", "HIGH", "BOLA/IDOR read resource", "DIDOKUMENTASIKAN", "Kode"],
    ["F-02", "HIGH", "Cross-cluster device command", "DIKENDALIKAN (RBAC)", "Kode"],
    ["F-03", "HIGH", ".env world-readable + rahasia bocor", "DISKRIP", "Infra"],
    ["F-04", "HIGH", "Tanpa rate limit IoT", "DIPERBAIKI", "Kode"],
    ["F-05", "MED", "Tanpa body-size limit", "DIPERBAIKI", "Kode"],
    ["F-06", "MED", "Future timestamp diterima", "DIPERBAIKI", "Kode"],
    ["F-07", "MED", "Cross-device telemetry injection", "SUDAH AMAN", "Kode"],
    ["F-08", "MED", "Vite dev server terekspos", "DISKRIP", "Infra"],
    ["F-09", "MED", "SSH password auth aktif", "DISKRIP", "Infra"],
    ["F-10", "MED", "Kredensial lemah/default", "DISKRIP (manual)", "Infra"],
    ["F-11", "MED", "GitHub PAT di filesystem", "DISKRIP", "Infra"],
    ["F-12", "LOW", "Error handling DELETE user 500", "N/A di versi ini", "Kode"],
    ["F-13", "LOW", "Security headers minim", "DIPERBAIKI", "Kode"],
    ["F-14", "LOW", "Dokumentasi API terekspos", "DIPERBAIKI", "Kode"],
    ["F-15", "LOW", "71 paket OS belum update", "DISKRIP", "Infra"],
    ["F-16", "LOW", "Secure flag cookie dari header client", "DIPERBAIKI", "Kode"],
    ["F-17", "LOW", "Command replay/duplicate", "DIPERBAIKI", "Kode"],
    ["F-18", "INFO", "Tailscale ACL perlu ditinjau", "DISKRIP (manual)", "Infra"],
]
tbl = Table(status_rows, colWidths=[14*mm, 20*mm, 62*mm, 40*mm, 18*mm], repeatRows=1)
ts = [
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3ccd6")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
]
sev_color = {"HIGH": RED, "MED": AMBER, "LOW": BLUE, "INFO": GREY}
for i, row in enumerate(status_rows[1:], start=1):
    ts.append(("TEXTCOLOR", (1, i), (1, i), sev_color.get(row[1], GREY)))
    ts.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
    if row[3].startswith("DIPERBAIKI") or row[3] == "SUDAH AMAN":
        ts.append(("TEXTCOLOR", (3, i), (3, i), GREEN))
        ts.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
tbl.setStyle(TableStyle(ts))
story.append(tbl)
sp(8)
p("<b>Keterangan status:</b> <i>DIPERBAIKI</i> = kode diubah & diverifikasi dengan test; "
  "<i>SUDAH AMAN</i> = sudah tertutup pada versi kode ini (diverifikasi); "
  "<i>DIKENDALIKAN</i> = ditutup oleh kontrol lain (RBAC); "
  "<i>DISKRIP</i> = dicakup oleh skrip <font face='Courier'>harden_infra.sh</font> untuk dijalankan di VPS; "
  "<i>N/A</i> = komponen tidak ada pada versi kode ini; "
  "<i>DIDOKUMENTASIKAN</i> = dijelaskan sebab tidak berlaku 1:1.", "Small")
story.append(PageBreak())

# ---------------------------------------------------------------------------
# DETAIL PER-TEMUAN (KODE)
# ---------------------------------------------------------------------------
p("2. Remediasi di Level Aplikasi (Kode)", "H1")
rule()

def finding(fid, sev, title, risk, action, files, verify, before=None, after=None, note=None):
    p(f"{fid} &nbsp;&middot;&nbsp; {sev} &nbsp;&middot;&nbsp; {title}", "H2")
    p(f"<b>Risiko.</b> {risk}")
    p(f"<b>Tindakan.</b> {action}")
    if before:
        p("<b>Sebelum:</b>", "Small"); code(before)
    if after:
        p("<b>Sesudah:</b>", "Small"); code(after)
    if note:
        p(f"<b>Catatan.</b> {note}")
    p(f"<b>Berkas.</b> <font face='Courier'>{files}</font>", "Small")
    p(f"<b>Verifikasi.</b> {verify}", "Small")
    rule()

finding(
    "F-04", "HIGH", "Rate limit IoT per-hub",
    "Endpoint ingest telemetri tanpa batas laju memungkinkan flooding (DoS), apalagi bila HUB_KEY bocor.",
    "Menambahkan fungsi kunci rate-limit berbasis identitas hub (header X-Hub-ID), lalu menerapkannya "
    "pada /api/iot, /api/iot/batch, dan /api/iot/unapproved. Batas dapat dikonfigurasi via env "
    "(IOT_RATE_LIMIT_PER_HUB, IOT_BATCH_RATE_LIMIT_PER_HUB). Bila header hub tidak ada, fallback ke IP.",
    "app/core/rate_limit.py, app/routers/iot.py, app/core/config.py",
    "Unit test get_hub_rate_key: header hub -> 'hub:<id>', tanpa header -> 'ip:<addr>' (PASS).",
    after="@limiter.limit(IOT_RATE_LIMIT_PER_HUB, key_func=get_hub_rate_key)\ndef receive_iot(...):",
)

finding(
    "F-05", "MEDIUM", "Batas ukuran body permintaan",
    "Tanpa batas Content-Length, body JSON 10 MB dapat memicu memory/CPU exhaustion.",
    "Middleware ASGI murni (BodySizeLimitMiddleware) menolak body > MAX_BODY_SIZE (default 1 MB) "
    "dengan HTTP 413, baik via header Content-Length maupun penghitungan byte streaming. "
    "Unggahan multipart/form-data dikecualikan karena sudah punya validasi ukuran sendiri (5 MB).",
    "app/core/security_middleware.py, app/main.py, app/core/config.py",
    "Test: POST /api/iot body > 1 MB -> 413 (PASS); body kecil tidak diblok (PASS); "
    "unggah floor-plan > 5 MB tetap 400 dari endpoint (PASS).",
    after='r = client.post("/api/iot", json={"DEV_ID":"x","DEV_NAME":"A"*1_050_000})\nassert r.status_code == 413',
)

finding(
    "F-06", "MEDIUM", "Tolak timestamp masa depan",
    "Telemetri dengan HUB_TS jauh di masa depan merusak integritas histori & alert.",
    "Fungsi _parse_event_time kini MENOLAK (HTTP 422) bila timestamp > now + 300 detik "
    "(toleransi clock-skew, dapat dikonfigurasi). Data lampau di luar jendela backfill tetap "
    "di-clamp ke waktu server agar tabel terpartisi tidak rusak.",
    "app/routers/iot.py, app/core/config.py",
    "Test test_parse_event_time_out_of_bounds_clamped: future > 300s -> HTTPException 422, "
    "tahun 2030 -> 422, lampau > 35 hari -> clamp (PASS).",
    before="max_bound = fallback_utc + timedelta(hours=24)\nif parsed_dt > max_bound: return fallback_utc  # diterima diam-diam",
    after="if parsed_dt > fallback_utc + timedelta(seconds=300):\n    raise HTTPException(422, 'timestamp too far in the future')",
)

finding(
    "F-07", "MEDIUM", "Injeksi telemetri lintas-device",
    "Hub seharusnya tidak dapat mengirim telemetri untuk device milik hub lain.",
    "Tidak diperlukan perubahan: kode ini sudah menolak bila device.hub_id != hub.hub_id (HTTP 403) "
    "pada /api/iot dan /api/iot/batch. Diverifikasi ulang.",
    "app/routers/iot.py (sudah ada)",
    "Dikonfirmasi lewat pembacaan kode dan test ingest yang memvalidasi kepemilikan hub (PASS).",
    after="if registered_device.hub_id != hub.hub_id:\n    raise HTTPException(403, 'Device does not belong to this hub')",
)

finding(
    "F-13", "LOW", "Security response headers",
    "Respons hanya memuat 'server: uvicorn' — tanpa HSTS, CSP, X-Content-Type-Options, dll.",
    "Middleware SecurityHeadersMiddleware menambahkan X-Content-Type-Options=nosniff, X-Frame-Options=DENY, "
    "Referrer-Policy=no-referrer, Permissions-Policy ketat, CSP minimal untuk API JSON, mengganti banner "
    "Server, dan HSTS (aktif saat produksi via ENABLE_HSTS).",
    "app/core/security_middleware.py, app/main.py",
    "Test: GET /api/health memuat semua header di atas & server=hubgate (PASS).",
    after="X-Content-Type-Options: nosniff | X-Frame-Options: DENY |\nReferrer-Policy: no-referrer | Content-Security-Policy: default-src 'none' ...",
)

finding(
    "F-14", "LOW", "Batasi dokumentasi API saat produksi",
    "/docs, /redoc, /openapi.json terbuka tanpa auth, membocorkan seluruh skema endpoint.",
    "Aplikasi dibuat dengan docs_url/redoc_url/openapi_url = None kecuali ENABLE_DOCS=true "
    "(default nonaktif saat ENV=prod).",
    "app/main.py, app/core/config.py",
    "Test: dengan ENABLE_DOCS=false -> /docs, /redoc, /openapi.json = 404; "
    "dengan ENABLE_DOCS=true -> /openapi.json = 200 (PASS).",
    after='docs_url="/docs" if ENABLE_DOCS else None  # idem redoc_url, openapi_url',
)

finding(
    "F-16", "LOW", "Secure flag cookie dari konfigurasi server",
    "Flag Secure pada cookie sesi ditentukan oleh header X-Forwarded-Proto yang dapat dipalsukan klien.",
    "Flag Secure kini dibaca dari konfigurasi server COOKIE_SECURE (default aktif saat produksi), "
    "diterapkan konsisten di login, logout, dan handler sesi kedaluwarsa. Header klien tidak lagi dipercaya.",
    "app/routers/auth.py, auth.py, app/core/config.py",
    "Test: COOKIE_SECURE=true -> config.COOKIE_SECURE True; =false -> False (PASS).",
    before='is_secure = request.headers.get("x-forwarded-proto") == "https"',
    after="from app.core.config import COOKIE_SECURE\nresponse.set_cookie(..., secure=COOKIE_SECURE, ...)",
)

finding(
    "F-17", "LOW", "Idempotency perintah device",
    "Perintah yang sama dikirim ulang menghasilkan command_id baru tanpa cek nonce/idempotency.",
    "Endpoint command menerima header opsional Idempotency-Key. Bila ada, command_id dibuat "
    "deterministik (uuid5 dari dev_id+key); pengiriman ulang mengembalikan perintah yang sudah "
    "ada (idempotent_replay) alih-alih menduplikasi. Race ditangani via try/except IntegrityError.",
    "app/routers/commands.py",
    "Test: dua POST dengan Idempotency-Key sama -> command_id identik & idempotent_replay=true; "
    "tanpa key -> command_id berbeda (backward compatible) (PASS).",
    after='command_id = uuid5(NAMESPACE_OID, f"cmd:{dev_id}:{idempotency_key}")\nif db.get(pending_commands, command_id): return {..., "idempotent_replay": True}',
)

# F-01, F-02, F-12 — honest documentation
p("F-01, F-02, F-12 &nbsp;&middot;&nbsp; Temuan yang tidak berlaku 1:1 pada versi kode ini", "H2")
p("<b>F-01 (BOLA/IDOR) &amp; F-02 (cross-cluster command).</b> Laporan menyebut akar masalah pola "
  "<font face='Courier'>if user_clusters and device.cluster_id not in user_clusters</font>. Pada snapshot "
  "kode ini <b>tidak ada model cluster maupun keanggotaan cluster</b> (model User hanya memiliki "
  "field role: admin/operator; tidak ada role viewer). Karena itu jalur kerentanan cross-cluster yang "
  "spesifik tidak dapat direproduksi di sini. Otorisasi perintah device tetap dibatasi RBAC "
  "(require_role(admin, operator)), dan verifikasi kepemilikan hub pada ingest sudah ada (lihat F-07). "
  "Rekomendasi: bila model cluster diperkenalkan kembali di produksi, terapkan penolakan eksplisit "
  "(default-deny) ketika pengguna non-root tidak memiliki akses ke cluster objek yang diminta, konsisten "
  "di devices/rooms/schedules/alerts/hubs.")
p("<b>F-12 (DELETE /api/admin/users -> 500).</b> Endpoint penghapusan user "
  "<font face='Courier'>/api/admin/users/{id}</font> <b>tidak ada</b> pada versi kode ini, sehingga tidak "
  "dapat diperbaiki secara langsung. Pola penanganan galat yang graceful (mis. 400/404/409, bukan 500) "
  "sudah diterapkan pada operasi penghapusan yang ada, contohnya DELETE /api/rooms yang menolak 400 bila "
  "masih ada device terpasang. Rekomendasi: saat endpoint hapus-user ditambahkan, bungkus operasi DB "
  "dengan try/except dan kembalikan 404 (tidak ditemukan) / 409 (konflik relasi).")
rule()

story.append(PageBreak())

# ---------------------------------------------------------------------------
# INFRA
# ---------------------------------------------------------------------------
p("3. Hardening Infrastruktur (skrip harden_infra.sh)", "H1")
rule()
p("Temuan tingkat host/infrastruktur dirangkum dalam skrip <font face='Courier'>server/harden_infra.sh</font> "
  "untuk dijalankan oleh administrator yang sah di VPS. Skrip bersifat <b>aman</b>: mode <i>dry-run</i> "
  "sebagai default (tidak mengubah apa pun), memerlukan <font face='Courier'>--apply</font> untuk menerapkan, "
  "membuat cadangan berkas sebelum diubah, serta <b>tidak</b> me-restart sshd atau mereboot secara otomatis.")
sp(4)
infra_rows = [
    ["ID", "Temuan", "Tindakan dalam skrip"],
    ["F-03", ".env world-readable", "chmod 600 pada server/.env + pengingat ROTASI HUB_KEY/CSRF_SECRET/DB password"],
    ["F-08", "Vite dev terekspos", "Panduan build produksi + bind 127.0.0.1; blokir :5173 via ufw"],
    ["F-09", "SSH password auth", "Drop-in 99-hardening.conf (PasswordAuthentication no) setelah cek authorized_keys; validasi sshd -t; restart manual"],
    ["F-10", "Kredensial lemah", "Daftar aksi manual: passwd OS, rotasi seed user app, ALTER ROLE Postgres"],
    ["F-11", "GitHub PAT bocor", "Rename direktori ghp_*@github.com + imbauan revoke token & clone via SSH"],
    ["F-15", "Paket OS usang", "apt update/upgrade + install & konfigurasi unattended-upgrades"],
    ["F-18", "Tailscale ACL", "Tampilkan tailscale status + imbauan tinjau ACL tailnet"],
    ["(DiD)", "Firewall", "ufw: izinkan 22/80/443, tolak 5173/8000 dari jaringan"],
]
itbl = Table(infra_rows, colWidths=[16*mm, 42*mm, 100*mm], repeatRows=1)
itbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3ccd6")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
]))
story.append(itbl)
sp(8)
p("<b>Cara pakai (di VPS, sebagai user alfido):</b>", "Small")
code("# 1) Tinjau dulu (tidak mengubah apa pun)\n./harden_infra.sh\n\n"
     "# 2) Terapkan langkah otomatis yang aman\n./harden_infra.sh --apply\n\n"
     "# 3) Kerjakan item 'ACTION REQUIRED (manual)': rotasi rahasia, ganti password,\n"
     "#    revoke PAT, lalu 'sudo systemctl restart ssh' & 'sudo ufw enable'.")
story.append(PageBreak())

# ---------------------------------------------------------------------------
# VERIFIKASI
# ---------------------------------------------------------------------------
p("4. Verifikasi & Pengujian", "H1")
rule()
p("Seluruh perubahan diverifikasi dengan menjalankan test suite backend. Karena harness test berbagi "
  "satu berkas SQLite, suite dijalankan per-berkas (mereset DB di antara berkas) agar hasil deterministik.")
ver_rows = [
    ["Skenario", "Hasil"],
    ["Baseline (kode asli), per-berkas", "254 lulus, 4 gagal"],
    ["Setelah patch (tanpa test baru), per-berkas", "254 lulus, 4 gagal (IDENTIK — 0 regresi)"],
    ["Setelah patch + test hardening baru", "263 lulus, 4 gagal"],
    ["Test hardening baru (test_hardening_pentest.py)", "9 lulus (F-04, F-05, F-13, F-14, F-16, F-17)"],
]
vtbl = Table(ver_rows, colWidths=[100*mm, 58*mm], repeatRows=1)
vtbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3ccd6")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(vtbl)
sp(8)
p("<b>Tentang 4 kegagalan pra-ada.</b> Keempatnya IDENTIK antara kode asli dan kode ter-patch, serta "
  "bersifat lingkungan — bukan akibat hardening: (1) test_milestone2_3 membutuhkan modul 'requests' yang "
  "tidak terpasang; (2) test_models_partitioning & (3-4) test_phase3_indexing_nullability bergantung pada "
  "migrasi Alembic/fitur partisi yang menyasar PostgreSQL, bukan SQLite uji.")
sp(6)
p("<b>Penyesuaian test akibat perubahan kontrak (bukan bug).</b> Dua berkas test disesuaikan agar sesuai "
  "perilaku baru F-06: test_partition_manager.py (future > 300s kini menimbulkan 422) dan "
  "test_phase6_verification_benchmark.py (payload benchmark memakai timestamp lampau yang realistis).")
sp(10)
p("5. Berkas yang Diubah / Ditambahkan", "H1")
rule()
code("app/core/config.py              (ubah)   konstanta hardening + helper env\n"
     "app/core/rate_limit.py          (ubah)   get_hub_rate_key (F-04)\n"
     "app/core/security_middleware.py (BARU)   body-size limit (F-05) + headers (F-13)\n"
     "app/main.py                     (ubah)   daftar middleware + docs guard (F-14)\n"
     "app/routers/iot.py              (ubah)   F-06 reject future + F-04 per-hub limit\n"
     "app/routers/commands.py         (ubah)   F-17 idempotency perintah\n"
     "app/routers/auth.py             (ubah)   F-16 cookie secure dari config\n"
     "auth.py                         (ubah)   F-16 cookie secure pada handler sesi\n"
     "harden_infra.sh                 (BARU)   skrip hardening infrastruktur\n"
     "test_hardening_pentest.py       (BARU)   9 test verifikasi hardening\n"
     "test_partition_manager.py       (ubah)   selaraskan dgn kontrak F-06\n"
     "test_phase6_verification_benchmark.py (ubah) timestamp realistis utk F-06")
sp(14)
p("— Selesai —", "SubTitle")

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cfd8e3"))
    canvas.line(20*mm, 14*mm, 190*mm, 14*mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(20*mm, 9*mm, "Laporan Hardening PMSR — dokumen internal")
    canvas.drawRightString(190*mm, 9*mm, f"Halaman {doc.page}")
    canvas.restoreState()

doc = SimpleDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=20*mm, rightMargin=20*mm, topMargin=18*mm, bottomMargin=20*mm,
    title="Laporan Hardening PMSR", author="Tim Hardening",
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(f"WROTE {OUTPUT}")
