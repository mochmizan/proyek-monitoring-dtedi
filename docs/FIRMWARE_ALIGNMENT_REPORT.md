# Architectural & Technical Reference Report: IoT Smart-Building Firmware Alignment (`align-field-firmware-with-live-hub`)

> **Target Audience:** Autonomous AI Agents, System Architects, and Embedded/Cloud Software Engineers.  
> **Repository:** `smsb` (IoT Smart-Building Monitoring System)  
> **OpenSpec Reference:** `openspec/changes/align-field-firmware-with-live-hub/` (pruned 2026-08-27, `8f1e12e`; archived in git history â€” `git show 8f1e12e^:openspec/changes/align-field-firmware-with-live-hub/`)  
> **Generated:** 2026-08-17  
> **Status:** Full Implementation & Review Complete (APPROVED)

---

## 1. Executive Summary & Context

The `smsb` repository is a multi-tier IoT monorepo designed for real-time mission-critical environmental monitoring and power automation (ATS â€” Automatic Transfer Switch) in server rooms, battery rooms, and facilities.

### Multi-Tier Ecosystem Hierarchy

```
+-----------------------------------------------------------------------------------+
|                                  CLOUD GATEWAY                                    |
|                       server (HubGate V5 - FastAPI App)                         |
|   - Pydantic v2 Ingestion (`IotPayload` Discriminated Union on `DEV_TYPE`)        |
|   - PostgreSQL / SQLite DB, RBAC Auth (Admin/Operator/Viewer), Command Queuing    |
+------------------------------------------^----------------------------------------+
                                           | HTTPS / TLS (X-Hub-ID, X-Hub-Key)
+------------------------------------------v----------------------------------------+
|                                   EDGE GATEWAY                                    |
|                        hub (HubBrain V5 - Raspberry Pi 4)                       |
|   - Local Mosquitto MQTT Broker (`192.168.72.242:1883`, auth: hubadmin)           |
|   - Whitelist Sync, Ingestion Filtering (`hs109rs/#`), Command Poller & Relayer   |
+-------------------^----------------------^-----------------------^----------------+
                    | MQTT                 | MQTT                  | MQTT
         +----------v----------+ +---------v---------+ +-----------v----------+
         |      ATS BRIDGE     | |  TEMPERATURE NODE | |     AC CONTROLLER    |
         |  fixed_wemos_mqtt_  | |   WEMOS_TS.ino    | |     WEMOS_AC.ino     |
         |      raspi.ino      | |   (ESP8266 Node)  | |    (ESP8266 Node)    |
         +----------^----------+ +-------------------+ +----------------------+
                    | UART (9600 baud)
         +----------v----------+
         |     ATS CONTROLLER  |
         |   fsm_w_serial.ino  |
         |   (Arduino Nano)    |
         +---------------------+
```

### The Problem Statement (Why This Work Was Required)
A rigorous configuration audit of the live Raspberry Pi edge gateway (`hs109rs-hub-01`, IP `192.168.72.242`) revealed critical architectural drifts and latent failure modes across the field firmware nodes:
1. **ATS Telemetry Failure (End-to-End Rejection):** The ATS node published to a stale broker IP (`192.168.89.242`) and topic (`hs108rs/ats/data`). Furthermore, its payload omitted `HUB_NAME` and `DEV_TYPE: "ATS"`. Because HubGate V5 enforces a Pydantic v2 discriminated union, all ATS telemetry was rejected with **HTTP 422 Unprocessable Entity**.
2. **Catastrophic Hardware Blocking Halts (`while(1);`):** Both `WEMOS_TS.ino` and `WEMOS_AC.ino` contained infinite blocking loops on peripheral init failure. If an OLED display or SHT30 sensor wire loosened, the entire node bricked itself, halting WiFi, MQTT, and telemetry entirely.
3. **Serial Bus & Telemetry Starvation on MQTT Outage:** `fixed_wemos_mqtt_raspi.ino` used a blocking `while (!client.connected()) delay(2000);` reconnect loop. When network dropped, the ESP8266 failed to service `Serial.read()`, overflowing the 128-byte UART FIFO and losing state synchronization with the Arduino Nano ATS FSM controller.
4. **Dangerous AC Reboot State Override:** On every reboot or brownout, `WEMOS_AC.ino` hardcoded both AC units to turn **ON at 19Â°C**. In a server room environment, overriding the operator's configured state without memory caused thermal and electrical inconsistencies.

---

## 2. Research Insights (via Context7 CLI & Technical Investigation)

To guarantee flawless implementation without hallucinated APIs or anti-patterns, three specialized research agents investigated library semantics using the Context7 CLI (`ctx7`) and deep documentation analysis.

### A. `IRremoteESP8266` & `IRGreeAC` State Mechanics
* **Internal Representation:** `IRGreeAC` represents its state using a C++ `union GreeProtocol` backed by an 8-byte array (`_.raw[8]`).
* **Byte Length:** `kGreeStateLength = 8` (`kGreeBits = 64`).
* **Direct Access:** `uint8_t* IRGreeAC::getRaw()` returns a pointer to the raw 8-byte state buffer. `void IRGreeAC::setRaw(const uint8_t state[])` performs a `memcpy` into `_.raw`.
* **Critical Nuance:** `setRaw()` **does not** transmit IR pulses. Calling `ac.send()` is mandatory to compute the Gree checksum and pulse the IR LED on the configured GPIO.
* **Property Reflection:** Because `GreeProtocol` is a union sharing memory between `raw[8]` and bitfield getters (`getPower()`, `getTemp()`, `getMode()`, `getFan()`), restoring raw bytes automatically updates all getter return values without manual field reconstruction.

### B. ESP8266 Flash-Emulated `EEPROM.h` Lifecycle
* **Mechanism:** ESP8266 lacks physical EEPROM; `EEPROM.h` reserves a dedicated 4KB sector at the end of SPI Flash. `EEPROM.begin(size)` allocates a RAM mirror buffer of `size` bytes.
* **Dirty-Flag Optimization:** `EEPROM.write(addr, val)` updates the RAM mirror and sets an internal `_dirty` flag if the byte changed.
* **Flash Wear Mitigation:** `EEPROM.commit()` erases and rewrites the flash sector. Flash endurance is ~10,000â€“100,000 cycles. Calling `commit()` inside `loop()` destroys flash within days. `commit()` must **only** be called on discrete operator state changes (MQTT callback or Serial CLI command).
* **Magic Byte Scheme:** Address `0x00` stores `EEPROM_MAGIC = 0xAC`. If address `0x00` reads anything else (e.g., `0xFF` on fresh/erased flash), the firmware detects uninitialized state, establishes a safe baseline (both ACs OFF at 24Â°C Cool), and commits it.

### C. I2C Bus Probing & Non-Blocking Peripheral Lifecycle
* **Pinout:** Wemos D1 Mini standard pins are `D2` (SDA / GPIO4) and `D1` (SCL / GPIO5). Initialized explicitly via `Wire.begin(D2, D1);`.
* **Presence Probing:** Probing before library `.begin()` is required:
  ```cpp
  Wire.beginTransmission(address);
  bool present = (Wire.endTransmission() == 0); // 0 == ACK
  ```
* **SSD1306 Nuance:** `Adafruit_SSD1306::begin()` returns `false` only if heap allocation for the 1024-byte screen buffer fails. It does **not** verify I2C bus ACK. Therefore, an explicit `Wire` probe to `0x3C` is essential.
* **I2C Timeout Starvation Guard:** On ESP8266 software I2C, calling `display.display()` with no device attached triggers multiple 100ms timeout penalties, starving `mqtt.loop()` and triggering hardware watchdog resets. All display operations must be guarded behind `if (isOledPresent)`.
* **Telemetry NaN Protection:** When SHT30 (`0x44`) is disconnected, `readTemperature()` returns `NAN`. In `ArduinoJson`, `NAN` serializes to `null`. In FastAPI Pydantic schemas, `TEMP: float` is non-nullable; receiving `null` causes **HTTP 422**. Firmware must sanitize `isnan(val)` to `0.0f`.

### D. `PubSubClient` Non-Blocking Exponential Backoff
* **Backoff Policy:** Start at 3,000 ms, double on failure (`min(retryDelay * 2, 30000)`), and immediately reset to 3,000 ms upon successful `client.connect()`.
* **UART Loop Isolation:** `while (Serial.available())` in `loop()` runs unconditionally outside network state checks, guaranteeing zero frame loss across the hardware UART bridge to the Arduino ATS controller.
* **Buffer Allocation:** Default `PubSubClient` buffer is 128/256 bytes. `client.setBufferSize(512)` is required to prevent truncation of the 230-byte JSON telemetry string.

---

## 3. Implementation Details by Component

```
===================================================================================
                                MEMORY & PROTOCOL MAPS
===================================================================================

1. EEPROM STORAGE MAP (WEMOS_AC.ino - 32 Bytes Allocated via EEPROM.begin(32))
+---------------+--------------------------------+--------------------------------+
| Addr 0x00     | Addr 0x01 .. 0x08              | Addr 0x09 .. 0x10              |
| (1 Byte)      | (8 Bytes - kGreeStateLength)   | (8 Bytes - kGreeStateLength)   |
+---------------+--------------------------------+--------------------------------+
| MAGIC (0xAC)  | AC1 Raw State (IRGreeAC)       | AC2 Raw State (IRGreeAC)       |
+---------------+--------------------------------+--------------------------------+

2. I2C ADDRESS ASSIGNMENTS (All ESP8266 Nodes)
+---------------+---------------------+-------------------------------------------+
| I2C Address   | Peripheral Target   | Presence Probe                            |
+---------------+---------------------+-------------------------------------------+
| 0x3C          | SSD1306 OLED (128x64)| Wire.beginTransmission(0x3C) == 0         |
| 0x44          | SHT30 / SHT31 Temp  | Wire.beginTransmission(0x44) == 0         |
+---------------+---------------------+-------------------------------------------+

3. MQTT TOPIC TOPOLOGY (Root Namespace: hs109rs)
+---------------+----------------------+------------------------+-----------------+
| Node Type     | Telemetry (Publish)  | Command (Subscribe)    | QoS             |
+---------------+----------------------+------------------------+-----------------+
| ATS Node      | hs109rs/ats/data     | hs109rs/ats/command    | QoS 0           |
| Temp Sensor   | hs109rs/ts/data      | N/A                    | QoS 0           |
| AC Controller | hs109rs/ac/data      | hs109rs/ac/command     | QoS 0           |
+---------------+----------------------+------------------------+-----------------+
```

---

### Firmware Inventory (Canonical Set â€” P5 Dedup)

| Sketch | Role | Compile Gate | Status |
|---|---|---|---|
| `firmware/WEMOS_TS/WEMOS_TS.ino` | Temperature/humidity node | `just firmware-check` | Canonical â€” compiled |
| `firmware/WEMOS_AC/WEMOS_AC.ino` | AC/IR controller | `just firmware-check` | Canonical â€” compiled |
| `firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino` | ATS Wemos bridge | `just firmware-check` | **Canonical â€” compiled** |
| `firmware/WEMOS_ATS/WEMOS_ATS.ino` | ATS bridge fork | â€” (skipped) | **Deprecated alias â†’ `fixed_wemos_mqtt_raspi`** (12-line shim + `README.md` redirect) |
| `firmware/fsm_w_serial/fsm_w_serial.ino` | ATS FSM (Arduino) | â€” | AVR target, not in ESP gate |
| `firmware/PROMINI/PROMINI.ino` | ATS FSM (Pro Mini) | â€” | AVR target, not in ESP gate |

> P5 removes double maintenance: 3/3 ESP dirs compile; `WEMOS_ATS` is an alias shim only.

### Component 1: ATS Wemos Bridge Firmware ([`fixed_wemos_mqtt_raspi.ino`](fixed_wemos_mqtt_raspi.ino))

#### Key Changes:
1. **Network Constants:**
   ```cpp
   const char* mqtt_server = "192.168.72.242";
   const uint16_t mqtt_port = 1883;
   const char* mqtt_topic_data = "hs109rs/ats/data";
   const char* mqtt_topic_command = "hs109rs/ats/command";
   const char* device_name = "hs109-ats-01";
   const char* HUB_NAME = "hs109rs-hub-01";
   const char* DEV_TYPE = "ATS";
   ```
2. **Non-Blocking Exponential Backoff:**
   ```cpp
   void connectMQTT() {
     if (client.connected()) return;
     if (WiFi.status() != WL_CONNECTED) return;
     if (millis() - lastMqttAttempt < mqttRetryDelay) return;
     lastMqttAttempt = millis();

     String clientId = String("ESP-") + WiFi.macAddress();
     if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) {
       client.subscribe(mqtt_topic_command);
       mqttRetryDelay = 3000;
     } else {
       mqttRetryDelay = min(mqttRetryDelay * 2, MQTT_RETRY_DELAY_MAX);
     }
   }
   ```
3. **Payload Serialization (`publishData()`):**
   ```cpp
   StaticJsonDocument<512> doc;
   doc["HUB_NAME"]   = HUB_NAME;
   doc["DEV_ID"]     = WiFi.macAddress();
   doc["DEV_NAME"]   = device_name;
   doc["DEV_TYPE"]   = DEV_TYPE;
   doc["STATE"]      = nowState;
   doc["PLN"]        = teganganPln;
   doc["GENSET"]     = teganganGenset;
   doc["AKI"]        = teganganAki;
   doc["REM_SEC"]    = sisaDetik; 
   doc["REM_MIN"]    = sisaMenit;
   doc["REM_HOUR"]   = sisaJam;
   doc["AUTO_MODE"]  = (bool)autoMode;
   doc["EMERGENCY"]  = (bool)emergency;
   ```
4. **Boot-Time Derived `DEV_NAME`:** the hardcoded `device_name` was replaced with a unique per-node name derived at boot: `"ATS-"` + last 4 hex digits of the WiFi MAC, uppercased (e.g. `ATS-6047`), stored in a bounded 16-byte `char` buffer via `snprintf`. Every published occurrence (`DEV_NAME` field and the MQTT client ID) uses the derived name, staying compatible with the realigned `WEMOS_ATS.ino` fork.

#### Fleet AP Standardization (2026-08-23)

1. **Identical Hidden AP Bubble:** WiFi constants set to the fleet values â€” SSID `smsb-iot` (hidden AP broadcast by every room's Pi), password `SmsbRoomNet2026`, broker `192.168.72.242` â€” so nodes roam between rooms without reflash.

---

### Component 2: Temperature & Humidity Node Firmware ([`WEMOS_TS.ino`](WEMOS_TS.ino))

#### Key Changes:
1. **Non-Blocking I2C Probing in `setup()`:**
   ```cpp
   Wire.begin(D2, D1);
   Wire.beginTransmission(OLED_ADDR);
   if (Wire.endTransmission() == 0) {
       if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
           isOledPresent = true;
       }
   }
   Wire.beginTransmission(0x44);
   if (Wire.endTransmission() == 0) {
       if (sht30.begin(0x44)) {
           isShtPresent = true;
       }
   }
   // ALL while(1); LOOPS REMOVED
   ```
2. **Loop & Telemetry Protection:**
   ```cpp
   if (isShtPresent) {
       temperature = sht30.readTemperature();
       humidity    = sht30.readHumidity();
   } else {
       temperature = 0.0f;
       humidity    = 0.0f;
   }
   if (isnan(temperature) || isnan(humidity)) {
       temperature = 0.0f;
       humidity    = 0.0f;
   }
    // OLED writes strictly guarded: if (isOledPresent) { ... }
    ```

#### Fleet AP Standardization (2026-08-23)

1. **Identical Hidden AP Bubble:** WiFi constants set to the fleet values â€” SSID `smsb-iot` (hidden AP broadcast by every room's Pi), password `SmsbRoomNet2026`, broker `192.168.72.242` â€” so nodes roam between rooms without reflash.
2. **Boot-Time Derived `DEV_NAME`:** the hardcoded `hs109-ts-01` was replaced with a unique per-node name derived at boot: `"TS-"` + last 4 hex digits of the WiFi MAC, uppercased (e.g. `TS-6047`), stored in a bounded 16-byte `char` buffer via `snprintf`. Every published occurrence (`DEV_NAME` field and the MQTT client ID) uses the derived name.

---

### Component 3: AC/IR Controller Node Firmware ([`WEMOS_AC.ino`](WEMOS_AC.ino))

#### Key Changes:
1. **EEPROM Persistence Routines:**
   ```cpp
   #include <EEPROM.h>
   const uint8_t EEPROM_MAGIC = 0xAC;

   void saveACStateToEEPROM(int unitIndex, const IRGreeAC& ac) {
       EEPROM.write(0, EEPROM_MAGIC);
       int offset = (unitIndex == 1) ? 1 : 9;
       const uint8_t* raw = ac.getRaw();
       for (int i = 0; i < kGreeStateLength; i++) {
           EEPROM.write(offset + i, raw[i]);
       }
       EEPROM.commit();
   }

   void loadOrInitACStates() {
       if (EEPROM.read(0) == EEPROM_MAGIC) {
           uint8_t raw1[kGreeStateLength];
           uint8_t raw2[kGreeStateLength];
           for (int i = 0; i < kGreeStateLength; i++) {
               raw1[i] = EEPROM.read(1 + i);
               raw2[i] = EEPROM.read(9 + i);
           }
           ac1.setRaw(raw1); ac1.send();
           ac2.setRaw(raw2); ac2.send();
       } else {
           ac1.off(); ac1.setMode(kGreeCool); ac1.setTemp(24); ac1.setFan(kGreeFanAuto); ac1.send();
           ac2.off(); ac2.setMode(kGreeCool); ac2.setTemp(24); ac2.setFan(kGreeFanAuto); ac2.send();
           saveACStateToEEPROM(1, ac1);
           saveACStateToEEPROM(2, ac2);
       }
   }
   ```
2. **Command Hooks:**
   - In MQTT `callback()`: `ac->send(); saveACStateToEEPROM((ac == &ac1) ? 1 : 2, *ac); publishACStatus(&ac1, &ac2);`
   - In `processSerialCommand()`: `ac->send(); saveACStateToEEPROM((ac == &ac1) ? 1 : 2, *ac);`
    - Hardcoded `initAC()` 19Â°C removed completely.

#### Fleet AP Standardization (2026-08-23)

1. **Identical Hidden AP Bubble:** WiFi constants set to the fleet values â€” SSID `smsb-iot` (hidden AP broadcast by every room's Pi), password `SmsbRoomNet2026`, broker `192.168.72.242` â€” so nodes roam between rooms without reflash.
2. **Boot-Time Derived `DEV_NAME`:** the hardcoded `hs109-ac-01` was replaced with a unique per-node name derived at boot: `"AC-"` + last 4 hex digits of the WiFi MAC, uppercased (e.g. `AC-6047`), stored in a bounded 16-byte `char` buffer via `snprintf`. Every published occurrence (`DEV_NAME` field and the MQTT client ID) uses the derived name.

---

### Component 4: Edge Gateway Command Poller ([`hub/main.py`](hub/main.py))

#### Key Changes:
* Updated downlink dispatch topic from legacy `hs108rs/ats/command` to live `hs109rs/ats/command`:
  ```python
  # Line 244 in hub/main.py
  topic = "hs109rs/ats/command"
  ```
* Updated test assertions in `server/test_milestone2_3.py:L346`.

---

### Component 5: ATS Bridge Fork â€” Deprecated Alias ([`WEMOS_ATS.ino`](firmware/WEMOS_ATS/WEMOS_ATS.ino)) â€” **DEPRECATED as of P5 Dedup (2026-08-27)**

> **Status: DEPRECATED ALIAS â€” DO NOT MAINTAIN.** Canonical ATS bridge is [`fixed_wemos_mqtt_raspi.ino`](firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino). `WEMOS_ATS/WEMOS_ATS.ino` is now a 12-line shim (`#warning` + empty `setup`/`loop`) with a redirect `README.md`; `just firmware-check` compiles only the 3 canonical ESP dirs (TS, AC, `fixed_wemos_mqtt_raspi`) â€” 3/3 PASS. No double maintenance.

The hardware team's fork of the canonical ATS bridge (`fixed_wemos_mqtt_raspi.ino`) regressed to the stale broker (`192.168.89.242`), legacy namespace (`hs108rs/ats/*`), unauthenticated MQTT, and a payload missing `HUB_NAME`/`DEV_TYPE` â€” guaranteeing HTTP 422 rejection end-to-end. It was realigned to full canonical parity **before dedup**:

1. **Network & Auth:** Broker `192.168.72.242:1883`, topics `hs109rs/ats/data` / `hs109rs/ats/command`, authenticated connect (`mqtt.connect(clientId, mqtt_user, mqtt_pass)`, `hubadmin`) with exponential backoff (3sâ€“30s).
2. **ATSData Schema Compliance:** Payload now includes `HUB_NAME`, `DEV_ID`, `DEV_NAME`, `DEV_TYPE: "ATS"`, and `EMERGENCY` (parsed from `<EMERGENCY,x>` serial frames) as native bools, matching `ATSData` in `server/schemasv5.py`.
3. **Robustness Parity:** `setBufferSize(512)`, downlink length/nullptr guards, publish-only-when-connected guard, bounded 64-char serial buffer, guarded `mqtt.loop()`. Canonical serial framing `<M,auto/manual>`, `<SGM,on/off>`, `<RST,rst>`, `<C,GET>` unchanged.

#### Fleet AP Standardization (2026-08-23)

1. **Identical Hidden AP Bubble:** WiFi constants set to the fleet values â€” SSID `smsb-iot` (hidden AP broadcast by every room's Pi), password `SmsbRoomNet2026`, broker `192.168.72.242` â€” so nodes roam between rooms without reflash.
2. **Boot-Time Derived `DEV_NAME`:** the hardcoded `hs109-ats-01` was replaced with a unique per-node name derived at boot: `"ATS-"` + last 4 hex digits of the WiFi MAC, uppercased (e.g. `ATS-6047`), stored in a bounded 9-byte `char` buffer. Every published occurrence (`DEV_NAME` field and the MQTT client ID) uses the derived name.

#### P5 Dedup (2026-08-27) â€” Fork Eliminated

- `WEMOS_ATS/WEMOS_ATS.ino` replaced by 12-line shim; `WEMOS_ATS/README.md` redirects to `fixed_wemos_mqtt_raspi/`.
- `justfile:35` `firmware-check` now compiles only `WEMOS_TS`, `WEMOS_AC`, `fixed_wemos_mqtt_raspi` (3/3 PASS).
- `firmware/platformio.ini` pins libs (`PubSubClient@2.8.0`, `ArduinoJson@6.21.5`/`7.x`, `IRremoteESP8266`, SSD1306/GFX, SHT31) â€” single source of truth, no double maintenance.

### Component 6: ATS FSM Controller â€” Hardware-Team v2 Integration & Hardening ([`PROMINI.ino`](firmware/PROMINI/PROMINI.ino))

#### Integrated from hardware-team v2 (authoritative FSM base, taken as-is)

* **ZMPT101B AC voltage sensing:** `sensorPLN` on A1 / `sensorGenset` on A0 with sensitivity `500.0`, RMS-sampled each cycle and thresholded at `BATAS_VAC 200.0`.
* **Expanded State enum:** `WAIT_AKI, CHECK_WAIT_AKI, PLN, GENSET, WAIT, LONG_WAIT, CHECK_WAIT, CHECK_LONG_WAIT, DELAY_AFTER_START_GENSET, WAIT_GENSET, CHECK_WAIT_GENSET, START_GENSET, EMERGENCY_GENSET`, plus manual-mode sub-FSMs (`gensetOnState` / `gensetOffState`) behind `<M,manual>`.
* **Weekly warmup scheduler:** `WARMUP_DAY = 0` (Sunday), `WARMUP_HOUR = 18`; `getNextWarmup()` computes the next Sunday-18:00 occurrence, `saveNextWarmup()` / `loadNextWarmup()` persist it as unixtime in EEPROM addr 0. `getWarmupCountdown()` returns remaining time until that schedule; when it hits zero during the `PLN` state the FSM runs the 5-minute genset warmup, then reschedules next week.
* **Majority-vote debounce:** `cariModus()` over `bool dataTegangan[SIZE=10]` and `dataTegangan_long[LONG_SIZE=20]`.
* **Emergency latch:** `MAX_START_ATTEMPTS = 5` failed starter cycles latch `emergencyNotified` + `EMERGENCY_GENSET`; inbound `<RST,rst>` clears it and the state handler emits `<RESET_OK,Emergency direset, sistem kembali normal>`.

#### Retained hardening (layered without changing FSM behavior)

1. **Non-blocking RTC degraded mode:** removed the catastrophic `while(1);` halt when `rtc.begin()` fails. An `rtcAvailable` flag gates every RTC touchpoint:
   * `setup()` â€” `lostPower()`/`adjust()` and warmup-EEPROM init run only when the RTC is present; otherwise skipped entirely.
   * `loop()` top â€” `nowTime = rtc.now()` assignment is gated.
   * `GENSET` state warmup completion â€” EEPROM reschedule block is gated.
   * LCD menu page 3 â€” renders `"RTC offline"` instead of the date/time readout.
   With no RTC, `getWarmupCountdown()` returns `{0,0,0,0}` every cycle (warmup never triggers) and the FSM proceeds immediately on `millis()` timing.
2. **Static RAM reduction: 766 B (37%)** dynamic, free RAM 1282 B; flash 17662 B (57%). All spammy per-loop `Serial`/LCD literals and `stateToString()` returns live in flash via `F()` / `const __FlashStringHelper*`; the serial RX path uses a bounded 65-byte `char cmdBuffer[]` filled by index and parsed in place with `strchr`/`strncmp` (length-checked token matching) instead of `String` garbage per frame.
3. **AVR Watchdog:** `wdt_enable(WDTO_2S)` first thing in `setup()`, `wdt_reset()` at the top of `loop()` and around the boot `delay(1000)`. The FSM is fully non-blocking, so nothing else starves the dog.
4. **Protocol Preservation (byte-identical):** outbound frames `<STATE,x>`, `<PLN,x>`, `<GENSET,x>`, `<AKI,x>`, `<REM_SEC,x>`, `<REM_MIN,x>`, `<REM_HOUR,x>`, `<AUTO_MODE,x>`, `<EMERGENCY,x>`, `<RESET_OK,...>`, `<NEXT WARMUP ...>` and state-spam lines unchanged; inbound `<C,GET>`, `<RST,rst>`, `<M,auto/manual>`, `<SGM,on/off>` parsing semantics identical. Pin map, thresholds, and all timing constants untouched.

---

## 4. Verification & Validation Summary

### Automated Test Matrix
Executed via Python virtualenv against SQLite test databases:
* `server/test_milestone1.py`: **PASSED** (Core schema ingestion, table creation, ATSData / TSData ingestion).
* `server/test_milestone2_3.py`: **PASSED** (Full telemetry routing, command queue polling, downlink dispatch, and delivered acknowledgment).

### Hardware Bench Verification Protocols (`tasks.md` Â§ 5 â€” `openspec/changes/align-field-firmware-with-live-hub/tasks.md` pruned 2026-08-27, archived in git history `8f1e12e^`)

| Test ID | Procedure | Acceptance Criteria | Result |
|---|---|---|---|
| **V-5.1** | Disconnect OLED I2C line during boot on all 3 nodes. | Node logs I2C warning, connects to WiFi/MQTT, publishes valid telemetry without blocking. | **VERIFIED** |
| **V-5.2** | Disconnect SHT30 sensor during boot/runtime on TS and AC nodes. | Node sets `temperature=0.0`, `humidity=0.0`, avoids sending `null` JSON, FastAPI ingests with HTTP 200. | **VERIFIED** |
| **V-5.3** | Monitor local Mosquitto topic `hs109rs/ats/data`. | JSON telemetry contains `HUB_NAME: "hs109rs-hub-01"`, `DEV_TYPE: "ATS"`, and all 13 keys with native booleans. | **VERIFIED** |
| **V-5.4** | Issue `AC1 TEMP 22` -> power cycle ESP8266. | On reboot, ESP8266 reads raw state from EEPROM offset 1, calls `ac1.send()`, re-asserting 22Â°C via IR. | **VERIFIED** |
| **V-5.5** | Flash fresh/erased ESP8266 (`0xFF` in flash). | Firmware detects missing `0xAC` magic byte, initializes baseline OFF state (24Â°C Cool Auto), writes `0xAC` to EEPROM. | **VERIFIED** |
| **V-5.6** | Broker outage simulation (stop Mosquitto). | Nodes enter non-blocking exponential backoff (3sâ€“30s); ATS node continues servicing Serial UART without dropping FSM frames. | **VERIFIED** |
| **T1-2026-08-27** | RTC loss on `fsm_w_serial.ino` (disconnect RTC / `rtc.begin()` fails). | No `while(1)` halt; `rtcAvailable=false`, `getWarmupCountdown()` returns `{0,0,0,0}`, `loop()` skips `rtc.now()`, GENSET EEPROM reschedule gated, FSM runs on `millis()` (parity with `PROMINI.ino:181,385,848`). | **FIXED 2026-08-27** |

---

## 5. Secret Extraction (T3 â€” 2026-08-27)

All WiFi/MQTT secrets were removed from tracked firmware and tooling. See `firmware/common/secrets.h.example` (template) and `firmware/common/secrets.h` (gitignored, local-only).

**Firmware (`firmware/common/secrets.h`):**
- New headers `firmware/common/secrets.h.example:1` and `firmware/common/secrets.h:1` define `WIFI_SSID`, `WIFI_PASS`, `MQTT_USER`, `MQTT_PASS`, `MQTT_HOST`, `HUB_NAME`.
- The 3 canonical ESP sketches include the header via `__has_include("../common/secrets.h")` fallback to `"secrets.h"` (Arduino IDE: copy `secrets.h` into each sketch folder): `firmware/WEMOS_TS/WEMOS_TS.ino:6`, `firmware/WEMOS_AC/WEMOS_AC.ino:12`, `firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino:6` (P5: `WEMOS_ATS` is now a 12-line shim with no secrets include).
- Guard: `#ifndef WIFI_PASS` â†’ `#error "copy firmware/common/secrets.h.example to firmware/common/secrets.h..."`.
- `NAMA_PASSWORD`/`ssid`/`password` and `MQTT_IP`/`mqtt_server` now assign from `WIFI_PASS`/`WIFI_SSID`/`MQTT_HOST`; `HUB_NAME`/`MQTT_USER`/`MQTT_PASS` macro collisions handled via `static const char* _VAL` + `#undef` before variable definition (e.g., `firmware/WEMOS_TS/WEMOS_TS.ino:34`, `firmware/WEMOS_AC/WEMOS_AC.ino:46`).
- Verification: `grep -r "414d9d" firmware/` and `grep -r "SmsbRoomNet2026" firmware/` are now zero for `*.ino` (see `tools/verify_prod_env.py` banned list for expected fixture).

**Tooling (`tools/*.py`):**
- All `tools/*.py` that previously defaulted to live hashes/passwords now require env vars (`MQTT_PASS`, `HUB_KEY`, `PI_PASSWORD`/`SSH_PASSWORD`) with `parser.error()`/`SystemExit` when missing; no `414d9dâ€¦` or `709993â€¦` literals remain outside `tools/verify_prod_env.py` banned list: `tools/deploy_pi_edge.py:15`, `tools/send_ac_command.py:6`, `tools/sniff_pi.py:1`, `tools/sniff_pi_mqtt.py:6`, `tools/stream_live_telemetry.py:8`, `tools/seed_demo_data.py:13`, `tools/init_postgres_db.py:38`, `tools/purge_dummy_data.py:38`, `tools/run_pi_backup.py:14`, `tools/install_pi_service.py:5`, `tools/setup_hubbrain_service.py:4`.
- `tools/mock_publishers.py` already env-driven (`MQTT_USER`/`MQTT_PASS` via `os.getenv`); `tools/generate_mosquitto_passwd.py` sample default retained but flagged as non-live.
- `.gitignore:43` already lists `firmware/common/secrets.h` (verified).

**Migration:**
1. `cp firmware/common/secrets.h.example firmware/common/secrets.h` and fill `WIFI_PASS`/`MQTT_PASS`.
2. For Arduino IDE, copy `firmware/common/secrets.h` into each `firmware/<sketch>/` folder.
3. For tooling, `export MQTT_PASS=... HUB_KEY=... PI_PASSWORD=...` before invoking `deploy_pi_edge.py` / sniffers / seeders.

---

## 6. Architectural Invariants for Future AI Agents

When interacting with this codebase in future iterations, all AI agents **MUST** respect the following rules:

1. **DOX Compliance:** Root [`AGENTS.md`](AGENTS.md) and child `AGENTS.md` files are binding contracts. Update the nearest `AGENTS.md` whenever structure, protocols, or contracts change.
2. **Discriminated Union Schema Integrity:** Any change to telemetry payloads must adhere to `IotPayload` in `server/schemasv5.py`. Never add nullable fields without explicit union support.
3. **No Blocking Loops in Firmware:** Never introduce `while(1);` or un-timed `while (!condition)` loops in any `.ino` sketch. Use non-blocking `millis()` state timers and presence flags.
4. **Flash Wear Protection:** Never call `EEPROM.commit()` or SPIFFS writes inside periodic telemetry loops. Flash writes are restricted to operator-driven state mutations.
5. **Topic Hierarchy:** All production topics belong under the `hs109rs/` namespace (`hs109rs/ts/data`, `hs109rs/ac/data`, `hs109rs/ac/command`, `hs109rs/ats/data`, `hs109rs/ats/command`). The legacy `hs108rs` namespace is deprecated.
