# SESSION HANDOVER DOCUMENT — SMSB IOT MONITORING PLATFORM

**Last Updated:** 2026-09-05
**Repository State:** main @ `b3b4462` | 395 tests green | lint/build clean | VPS LIVE | history downsampled + gap-aware chart live | scheduler visual builder shipped `b3b4462`
**Current Blocker:** none — system is deployed and serving campus-wide

---

## 1. Current Live State (verified on site 2026-08-24)

### A. Dashboard & Access
| Access path | URL |
|---|---|
| Campus devices / WiFi | `https://10.33.102.172/` (primary) |
| Remote admin (tailnet only) | `https://100.108.98.30` |
| Public IP inbound | **BLOCKED by Azure/campus NSG** — not usable |

- nginx `hubgate` site now runs the **repo's `deploy/nginx_smsb.conf`**: SPA served from `/var/www/gui-app`, `/api/` proxied to uvicorn, certs `/etc/nginx/ssl/smsb.crt|.key` reissued with `IP:10.33.102.172` SAN. Old friend-era all-proxy config backed up at `/home/genset/hubgate.bak.*`.
- History API: downsamples to ~1000 time buckets via AVG when >1000 rows (was `ORDER BY ASC LIMIT 1000` returning only ~11 min for ATS at 1.5 Hz). Frontend chart is gap-aware: `5 min / 10×median` threshold breaks lines, shades offline spans (including leading window-start→first-point) and renders isolated dots.
- Unknown ESP device `68:C6:3A:D7:60:47` keeps transmitting & is auto-reported unapproved — needs pairing/approval or removal.

### B. Cloud Gateway — VPS `genset` (LIVE)
| Aspect | Value |
|---|---|
| OS / size | Ubuntu 24.04, 1 GB RAM |
| Addresses | campus-internal **`10.33.102.172`**, Tailscale `100.108.98.30`, public `202.43.94.30` |
| App | FastAPI `smsb-api.service` :8000 behind nginx (`hubgate` site), SPA at `/var/www/gui-app` |
| Deploy | bare repo `/opt/smsb.git` + post-receive hook ← `git push prod main`; worktree `/opt/smsb`; SQLite DB `/opt/smsb/server/hubgatev5.db` |
| TLS | self-signed `/etc/nginx/ssl/smsb.crt|.key`, SANs include `10.33.102.172`, Tailscale IP, public IP |
| **NTP** | VPS is now an NTP server for campus IoT hubs: chrony `allow 10.33.0.0/16`, UFW allows `123/udp from 10.33.0.0/16` |

### C. Edge Hub — Raspberry Pi (LIVE)
> Naming note: Pi **hostname** is `hs108rs-hub-01`; its registered **hub identity** / MQTT prefix is `hs109rs-hub-01` / `hs109rs/#` (`.env HUB_NAME=hs109rs-hub-01`, legacy room naming). Both are correct in context.
| Aspect | Value |
|---|---|
| Bubble AP | hidden `smsb-iot` @ `192.168.72.242`, moved off crowded ch11 to a quieter channel (hostapd-only change; fleet firmware scans all channels). Channel survey found ch11 with 8 APs (UGM-Hotspot/Secure/Guest, eduroam, STARLINK) |
| Wall port | eth0 cabled to UGM wall port → `[SYNC SUCCESS]` flowing; VPS↔Pi ping 0% loss. Static `10.33.102.10/24` (server segment, moved from 10.33.36.81) + default via `10.33.102.254` *(fix current file still via 10.33.36.254 — not on-link)* |
| Networking | netplan = **eth0 ONLY** (`dhcp4:true` + static `10.33.102.10/24` + default via gateway). wlan0 IP from `/etc/systemd/system/wlan0-addr.service` (oneshot, After=hostapd.service). Real dnsmasq config = `/etc/dnsmasq.d/smsb-ap.conf`; main conf stays empty |
| Clock | Pi has NO RTC battery and NO internet (wall port is LAN-only); chrony client → `server 10.33.102.172 iburst prefer` (chrony 4.8, NOT timesyncd; NTS pool sources disabled), makestep corrects fake boot clock within seconds |
| Services | `hubbrain.service`, mosquitto :1883, hostapd + dnsmasq |

### D. ESP Nodes
All 5 sketches fleet-standardized on `smsb-iot` @ `192.168.72.242`, boot-derived `DEV_NAME`. See `FIRMWARE_ALIGNMENT_REPORT.md`.

---

## 2. Deployment Path (resolved & proven)

The internal campus-LAN path is the chosen deployment path: Pi → UGM wall port → campus routing → VPS `10.33.102.172`. SERVER_URL points at `https://10.33.102.172/api/*` — zero dependence on the public IP / Azure NSG. Campus WiFi clients reach the dashboard directly (no VPN); admin access from anywhere via Tailscale.

Historical debugging notes (netplan wlan0 drop rules, dnsmasq duplicate-keyword failure, usbipd-win SD-card editing workflow) are preserved in git history of this file and in `hub/AGENTS.md`.

---

## 3. Standing Decisions & Constraints

- **No Tailscale on the Pi** — plain HTTPS to VPS only. Tailscale kept for laptop/VPS admin.
- **Fleet bubble is global & identical** on every hub Pi: hidden `smsb-iot` @ `192.168.72.242` (password per fleet standard — see `FIRMWARE_ALIGNMENT_REPORT.md`). Never per-room reflash.
- **MQTT-only bus isolation verified**: ip_forward=0, no NAT, DNS off on the Pi.
- Don't trust Starlink-hotspot port probes (CGNAT fake-ACKs all ports).
- Rotate before public handover: `genset` VPS user password, `hubadmin` pw, MQTT_PASS; sanitize `tests/test_verify_prod_env.py` L111/L113.
- Set `HUB_BOOTSTRAP_KEY` env on VPS before pairing any NEW hub (existing hub identity already pinned).
- Never put wifi stanzas in Pi netplan (see `hub/AGENTS.md`); never edit `/etc/dnsmasq.conf` on the Pi (keep it empty/comment-only).

## 4. Local Dev Resume (unchanged)

```powershell
just dev                 # API :8000 + SPA :5173 (justfile runner)
pytest                 # full suite (395 tests: 217 server + 13 hub + 15 integration + 150 vitest)
cd dashboard; npm run lint; npm run build
```
Dashboard logins: `admin/admin123`, `operator/operator123`, `viewer/viewer123`.


