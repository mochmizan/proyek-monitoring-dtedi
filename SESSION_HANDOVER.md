# SESSION HANDOVER DOCUMENT — SMSB IOT MONITORING PLATFORM

**Last Updated:** August 21, 2026  
**Repository State:** Central Gateway & Edge Active | 100/100 Pytest Passing | AC IR Control & Jakarta Time Aligned  

---

## 1. Executive Summary & Verified Capabilities

### A. Central Gateway (HubGate V5) & Database
- **FastAPI Backend:** Runs on port `8000` (`SERVERv5/v5/hubgatev5.py`).
- **Database:** Persistent SQLite at `SERVERv5/v5/hubgatev5.db` with registered users (`admin`, `operator`, `viewer`), device pairings, and time-series telemetry.
- **Heartbeat & Presence:** 25s timeout state machine automatically detects online/offline transitions and auto-resolves alerts.
- **Device Authorization:** Strict MAC authorization and unapproved device reporting.
- **Authentication & RBAC:** Argon2id hashed passwords with sliding session cookies.

### B. Edge Gateway (HubBrain V5 on Raspberry Pi `10.33.36.81`)
- **Systemd Service:** `hubbrain.service` (`enabled` on boot).
- **Mosquitto Broker:** Runs on port `1883` (`enabled` on boot).
- **Fast Command Polling:** Polling loop interval set to **2s** for sub-2-second IR command delivery to hardware.
- **Offline Cache:** SQLite WAL buffering (`edge_cache.db`) with FIFO paced replay upon upstream reconnection.
- **Dynamic Topic Resolution:** Maps downlink commands dynamically to `{hub_name}/{dev_type}/command` (e.g. `hs109rs/ac/command`).

### C. Physical Hardware Nodes & Firmware
- **Physical AC Node:** MAC `98:F4:AB:F4:AD:A2` (ESP8266 + Gree IR transmitters + SHT30).
  - Listens to: `hs109rs/ac/command`.
  - Transmits live telemetry to: `hs109rs/ac/data`.
  - Supports: `ON`, `OFF`, `SET_TEMP` (16°C–30°C), EEPROM state persistence (`0xAC` magic byte).
- **Physical TS Node:** SHT30 temperature/humidity sensor + OLED.

### D. Frontend SPA (React 19 + TanStack Query + Tailwind 4)
- **Timeframe Scaling:** `6h`, `24h`, `7d`, `30d` interactive range selector with URL sync and time-proportional X-axis distribution.
- **Jakarta Time (WIB / UTC+7):** All chart axes, ticks, and hover tooltips render explicitly in Jakarta Local Time.
- **Air Conditioner Control Panel:** Full interactive UI supporting target AC selection (`Unit AC 1` / `Unit AC 2`), power control (`Power ON` / `Power OFF`), and temperature setpoint slider.

---

## 2. Physical Network & Topology Reference

| Entity | IP Address | Credentials / Port | Status / Role |
|---|---|---|---|
| **Windows Laptop (Dev Host)** | `10.33.36.80` | `localhost:5173` (SPA), `localhost:8000` (API) | Central Gateway & Web Dashboard |
| **Raspberry Pi (Ethernet)** | `10.33.36.81` | `hubadmin` / `hubadmin` (SSH port 22) | Edge Bridge Gateway (`hubbrain.service`) |
| **Raspberry Pi AP (wlan0)** | `192.168.72.242` | SSID: `ABC` / Pass: `Admin123` | Local IoT Wi-Fi Hotspot |
| **Mosquitto MQTT Broker** | `192.168.72.242:1883` | User: `hubadmin` / Pass: `414d9...` | Edge Message Broker |
| **Physical AC Node** | DHCP via AP `ABC` | MAC: `98:F4:AB:F4:AD:A2` | Active, streaming telemetry every 5s |

---

## 3. How to Resume Services After Laptop Restart

### Option A: 1-Click Launchers (Recommended)
Simply double-click or run from repository root:
* **Batch Launcher:** `start_dev.bat`  
  *or*
* **PowerShell Launcher:** `powershell -ExecutionPolicy Bypass -File .\start_dev.ps1`

### Option B: Manual Terminal Startup
If you prefer running services in separate terminals:

```powershell
# Terminal 1: Start Central Backend
cd C:\Users\Mizan\Documents\smsb\SERVERv5\v5
python -m uvicorn hubgatev5:api --host 0.0.0.0 --port 8000

# Terminal 2: Start Frontend SPA Dev Server
cd C:\Users\Mizan\Documents\smsb\clients\gui-app
npm run dev
```

### Accessing the Dashboard:
* Open **`http://localhost:5173`** in your browser.
* **Credentials:**
  - `admin` / `admin123`
  - `operator` / `operator123`
  - `viewer` / `viewer123`

---

## 4. Verification Commands

```powershell
# 1. Run full automated test suite across repo (100 tests)
pytest

# 2. Frontend lint & build check
cd clients\gui-app
npm run lint
npm run build
```
