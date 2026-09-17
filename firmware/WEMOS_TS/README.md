# WEMOS_TS — Temperature & Humidity Sensor Node Firmware

ESP8266-based temperature and humidity monitoring node deployed in server rooms and power distribution enclosures.

## Overview
- **Board**: LOLIN(WEMOS) D1 R2 & mini (ESP8266)
- **Target Node**: Temperature & Humidity Sensor (SHT30 / SHT31)
- **I2C Peripherals**:
  - Sensirion SHT30/SHT31 Temperature & Humidity Sensor (`0x44` primary, `0x45` alternate)
  - SSD1306 128x64 OLED Display (`0x3C` primary, `0x3D` alternate)
- **MQTT Topics**:
  - Publish: `hs109rs/ts/data`

## Telemetry Cadence & Report-by-Exception (RBE)
- **Steady-State Heartbeat**: 300,000 ms (5 minutes / 300s)
- **Sensor Sampling**: 2,000 ms (2s) non-blocking I2C polling
- **OLED Display Refresh**: 1,000 ms (1 Hz) responsive rendering
- **Deadband Thresholds**:
  - $\Delta T \ge 0.2^\circ\text{C}$
  - $\Delta\text{RH} \ge 2.0\%$
- **Rate-Limit (Min Publish Interval)**: 5,000 ms (5s) to suppress noise chatter
- **Resilience**: Instant force publish upon sensor fault (`STATUS: SENSOR_ERROR`, null temp/humid) or recovery (`STATUS: OK`)

## Compilation (Arduino IDE)
1. Install **ESP8266 Board Core** (`https://arduino.esp8266.com/stable/package_esp8266com_index.json`).
2. Install Required Libraries:
   - `PubSubClient` (v2.8.0 by Nick O'Leary)
   - `ArduinoJson` (**v6.21.5** — DO NOT use v7)
   - `Adafruit SSD1306` & `Adafruit GFX Library`
   - `Adafruit SHT31 Library`
3. Open `WEMOS_TS.ino` in Arduino IDE.
4. Verify credentials in sketch-local `secrets.h`.
5. Select Board: **LOLIN(WEMOS) D1 R2 & mini**, Port: USB Serial port.
6. Click **Verify / Compile** (Ctrl+R) -> **Upload** (Ctrl+U).
