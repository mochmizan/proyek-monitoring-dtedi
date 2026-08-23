# HubGate V5 Local Testing & Development Guide

Comprehensive guide for running and testing the complete **HubGate V5 / HubBrain V5 IoT Platform** locally using Docker Compose, FastAPI backend, Vite React frontend, and mock telemetry publishers.

---

## 1. Architecture Overview

```mermaid
flowchart LR
    subgraph Local Hardware / Mock Layer
        M1[Mock TS Node] -->|MQTT hs109rs/ts/data| MOSQ[Mosquitto Broker :1883]
        M2[Mock ATS Node] -->|MQTT hs109rs/ats/data| MOSQ
        M3[Mock AC Node] -->|MQTT hs109rs/ac/data| MOSQ
        MOSQ -->|Downlink Commands| M2
        MOSQ -->|Downlink Commands| M3
    end

    subgraph Edge Layer
        MOSQ -->|Subscribe hs109rs/#| HB[HubBrain Gateway\nHUBV5/V5/main.py]
        HB -->|Buffer on Outage| EC[(SQLite WAL Cache\nedge_cache.db)]
    end

    subgraph Cloud / Central Server Layer
        HB -->|HTTP/HTTPS POST /api/iot| HG[HubGate API\nFastAPI :8000]
        HG -->|Persist Telemetry & Alerts| PG[(PostgreSQL :5432\nsmsb_prod)]
    end

    subgraph Frontend SPA
        SPA[React 19 + TanStack Query\nclients/gui-app :5173] -->|Vite Proxy /api| HG
    end
```

---

## 2. Prerequisites

Ensure you have the following installed on your local system:
- **Docker & Docker Compose** (v2.0+)
- **Python 3.10+** (Python 3.10 - 3.14 supported)
- **Node.js 18+** & **npm**

---

## 3. Environment Configuration (`.env`)

### A. Central Backend (`SERVERv5/v5/.env`)
Create or update `SERVERv5/v5/.env`:
```env
# Database connection URL (PostgreSQL Docker container)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/smsb_prod

# Seed credentials for initial Hub registration
HUB_NAME=hs109rs-hub-01
HUB_KEY=strong_local_hub_key_1234567890abcdef

# CORS configuration for Vite Frontend Dev Server
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### B. Edge Gateway (`HUBV5/V5/.env`)
Create or update `HUBV5/V5/.env`:
```env
# Local Eclipse Mosquitto Broker Configuration
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TOPIC=hs109rs/#
MQTT_USER=hubadmin
MQTT_PASS=hubadmin_local_secret_pass_2026

# Gateway Hub Identity (Must match hub_table in HubGate Server)
HUB_ID=hs109rs-hub-01
HUB_KEY=strong_local_hub_key_1234567890abcdef

# HubGate Server HTTP API Endpoints
SERVER_URL=http://localhost:8000/api/iot
SERVER_DEVICES_URL=http://localhost:8000/api/devices
SERVER_ALERT_URL=http://localhost:8000/api/iot/unapproved
SERVER_COMMANDS_URL=http://localhost:8000/api/hub/commands

# TLS Certificate pinning (Leave empty for HTTP local testing)
TLS_CERT_PATH=

# Local SQLite WAL Edge Buffer Database Path
EDGE_CACHE_DB_PATH=edge_cache.db
```

---

## 4. Step-by-Step Execution Guide

### Step 1: Start Docker Infrastructure Stack
Start PostgreSQL and Eclipse Mosquitto containers:
```bash
docker compose up -d
```
Verify both containers are healthy:
```bash
docker compose ps
```

*(Optional: If you wish to change the default MQTT password, run `python tools/generate_mosquitto_passwd.py --user hubadmin --password <new_password>` and restart mosquitto with `docker compose restart mosquitto`.)*

---

### Step 2: Initialize Database & Seed Admin User
From `SERVERv5/v5/`:
```bash
# 1. Run migrations and create tables (also seeds default Hub hs109rs-hub-01)
python SERVERv5/v5/init_sqlv5.py

# 2. Create the initial Admin user
python SERVERv5/v5/create_admin_user.py --username admin --password adminpassword123 --display-name "System Admin" --role admin
```

---

### Step 3: Run HubGate API Server
From `SERVERv5/v5/` (or repository root):
```bash
cd SERVERv5/v5
uvicorn hubgatev5:api --host 0.0.0.0 --port 8000 --reload
```
API Documentation is accessible at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### Step 4: Run HubBrain Edge Gateway
In a second terminal, start the edge gateway:
```bash
cd HUBV5/V5
python main.py
```
HubBrain connects to Mosquitto at `localhost:1883`, synchronizes device whitelist with HubGate, and starts polling for downlink commands and background cache replay.

---

### Step 5: Run Frontend SPA
In a third terminal, run the Vite frontend development server:
```bash
cd clients/gui-app
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser:
- Log in with username: `admin` and password: `adminpassword123`.

---

### Step 6: Run Mock Telemetry Publishers
In a fourth terminal, start the mock node publisher to simulate live field telemetry:
```bash
# Publish continuous TS, ATS, and AC telemetry every 5 seconds
python tools/mock_publishers.py --loop --interval 5.0
```

#### Additional Mock Publisher CLI options:
- **Publish specific device type only**:
  ```bash
  python tools/mock_publishers.py --type ts --temp 24.5 --humid 55.0
  python tools/mock_publishers.py --type ats --state PLN --pln 220.5 --auto-mode
  python tools/mock_publishers.py --type ac
  ```
- **Trigger Critical Temperature Alert**:
  ```bash
  python tools/mock_publishers.py --type ts --temp 35.5
  ```
- **Listen for Downlink Commands**:
  ```bash
  python tools/mock_publishers.py --listen
  ```

---

## 5. End-to-End Verification Checklist

| Test Scenario | Steps to Verify | Expected Result |
| :--- | :--- | :--- |
| **1. Telemetry Ingestion (Task 8.5)** | Run `mock_publishers.py --type ats`. | Telemetry flows: `Mock -> Mosquitto -> HubBrain -> HubGate`. Row appears in `ats_data` table. |
| **2. Device Auto-Discovery & Pairing** | Send telemetry for a new MAC (e.g. `AA:BB:CC:DD:EE:99`). Open UI **Settings > Device Pairing**. | Device appears under **Pending Devices**. Admin pairs it with a room, thresholds, and floor map coordinates. |
| **3. Live Dashboard Updates** | Navigate to Room Detail view on UI (`http://localhost:5173/rooms/...`). | Dashboard widgets auto-refresh every 2–5s reflecting live temperature, humidity, and ATS status without manual reload. |
| **4. Threshold Alert & Hysteresis** | Publish high temp: `mock_publishers.py --type ts --temp 36.0`. | Alert badge appears in UI header and active alert is logged in `/alerts`. Publishing `22.0°C` resolves the alert automatically. |
| **5. Downlink Commands** | Trigger AC/ATS command from UI or API (`POST /api/devices/{id}/command`). | HubBrain polls command, dispatches to MQTT topic (`hs109rs/ats/command` or `hs109rs/ac/command`), and marks `DELIVERED`. |
| **6. Edge Offline Cache Resiliency** | Stop HubGate (`Ctrl+C` in API terminal). Publish telemetry. Restart HubGate. | HubBrain writes payloads to `edge_cache.db`. Upon restart, the replay worker drains backlog and persists all records to DB. |

---

## 6. Automated Pipeline Integration Tests

To run the automated end-to-end integration test suite:
```bash
pytest tests/test_e2e_pipeline.py -v
```

To run all project test suites (backend, auth, edge, and pipeline):
```bash
pytest
```
