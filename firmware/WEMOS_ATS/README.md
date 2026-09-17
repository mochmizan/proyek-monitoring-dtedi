# WEMOS_ATS — Canonical ATS MQTT Bridge Firmware

Canonical ATS ESP8266 network bridge sketch connecting the ATS ATmega328P Pro Mini to the SMSB Hub MQTT broker.

## Overview
- **Board**: LOLIN(WEMOS) D1 R2 & mini (ESP8266)
- **Target Node**: `68:C6:3A:D7:60:47` (HS109SR-ATS / Switchboard ATS Unit)
- **Protocol**: Bidirectional UART bridging with Pro Mini at 9600 baud (`<STATE,...>`, `<PLN,...>`, `<GENSET,...>`, `<SGM,on>`, `<RST,rst>`)
- **Pro Mini Serial Polling**: Non-blocking decoupled polling every 500ms when connected (throttled 2,000ms when disconnected)
- **MQTT Topics**:
  - Publish: `hs109rs/ats/data`
  - Subscribe: `hs109rs/ats/command`

## Telemetry Cadence, Burst Mode & Deadbands (Phase 3)
- **Steady-State Heartbeat**: 60,000 ms (60s / 1 minute)
- **Dynamic Transient Burst Mode**:
  - Activated by any discrete state change from Pro Mini (`nowState`, `autoMode`, `emergency`, `pln_relay`, `gen_relay`, `alarm`).
  - **Instant 0ms bypass forward** for the first packet on state transition.
  - Subsequent burst reports at **2.0s interval for 60 seconds** during blackout, cranking, and load transfer.
- **Electrical Deadbands (Steady-State)**:
  - $\Delta V_\text{PLN} \ge 1.0\text{V}$
  - $\Delta V_\text{GENSET} \ge 1.0\text{V}$
  - $\Delta V_\text{AKI} \ge 0.1\text{V}$
  - Rate-limit (min publish interval): 2,000 ms (2s)
- **Serial Buffer Safety**:
  - Bounded static parsing buffer `char[65]` for UART frames
  - Bounded JSON payload buffer `char[512]` and `StaticJsonDocument<512>`
  - `client.setBufferSize(512)` to prevent overflow or dynamic heap churn

## Compilation (Arduino IDE)
1. Install **ESP8266 Board Core** (`https://arduino.esp8266.com/stable/package_esp8266com_index.json`).
2. Install Required Libraries via Library Manager:
   - `PubSubClient` (by Nick O'Leary)
   - `ArduinoJson` (**v6.21.5** — DO NOT use v7)
   - `Adafruit SSD1306` & `Adafruit GFX Library`
3. Open `WEMOS_ATS.ino` in Arduino IDE.
4. Verify credentials in `secrets.h` (already present in sketch folder).
5. Select Board: **LOLIN(WEMOS) D1 R2 & mini**, Port: USB Serial port.
6. Click **Verify / Compile** (Ctrl+R) -> **Upload** (Ctrl+U).
