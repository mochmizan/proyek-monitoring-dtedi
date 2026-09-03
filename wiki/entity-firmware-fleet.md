---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-ats-firmware-chain.md, wiki/concept-edge-resilience.md, wiki/concept-telemetry-pipeline.md, wiki/concept-command-path.md, wiki/workstream-firmware-proofing.md]
sources: [firmware/PROMINI/PROMINI.ino, firmware/WEMOS_ATS/WEMOS_ATS.ino, firmware/WEMOS_TS/WEMOS_TS.ino, firmware/WEMOS_AC/WEMOS_AC.ino, firmware/common/secrets.h.example, firmware/platformio.ini, docs/FIRMWARE_ALIGNMENT_REPORT.md, docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md]
updated: 2026-09-03
---

# Firmware Fleet Specifications

The `firmware/` subsystem encompasses embedded software for four hardware node types deployed across server and power distribution facilities. Nodes communicate locally over I2C, UART, and IEEE 802.11 b/g/n Wi-Fi, bridging telemetry to the local Raspberry Pi edge gateway (`HubBrain V5`) via MQTT.

```
+-----------------------------------------------------------------------------+
|                      LOCAL EDGE GATEWAY (Raspberry Pi 4)                    |
|                        Mosquitto MQTT: 192.168.72.242:1883                  |
+-------------------^-----------------------^---------------------^-----------+
                    | MQTT (QoS 0)          | MQTT (QoS 0)        | MQTT (QoS 0)
+-------------------v-----------+ +---------v---------+ +---------v-----------+
|          ATS BRIDGE           | | TEMPERATURE NODE  | |    AC CONTROLLER    |
|       WEMOS_ATS (ESP8266)     | | WEMOS_TS (ESP8266)| | WEMOS_AC (ESP8266)  |
|      Topic: hs109rs/ats/*     | |Topic: hs109rs/ts/*| | Topic: hs109rs/ac/* |
+-------------------^-----------+ +-------------------+ +---------------------+
                    | UART (9600 baud, 8-N-1)
+-------------------v-----------+
|         ATS CONTROLLER        |
|      PROMINI (ATmega328P)     |
|   FSM + Contactor Relays      |
+-------------------------------+
```

---

## 1. Node Hardware Specifications & MCU Pinouts

### 1.1 ATS FSM Controller (`firmware/PROMINI/PROMINI.ino`)
- **Microcontroller**: Microchip ATmega328P (Arduino Pro Mini 5V, 16 MHz external resonator).
- **Memory**: 32 KB Flash, 2 KB SRAM, 1 KB internal EEPROM.
- **Operating Voltage**: 5.0 V DC regulated.
- **Pin Map**:
  | Pin | Mode / Type | Signal / Identifier | Connected Component & Function |
  |---|---|---|---|
  | `A0` | Analog Input | `sensorGenset` | ZMPT101B AC voltage transformer (Generator Phase L-N) |
  | `A1` | Analog Input | `sensorPLN` | ZMPT101B AC voltage transformer (Mains Grid Phase L-N) |
  | `A2` | Analog Input | `akiPin` | Resistor voltage divider (12V starter battery, 0–25V scaled) |
  | `A4` | Bidirectional | Hardware I2C SDA | DS3231 RTC (`0x68`) and PCF8574 LCD backpack (`0x27`) |
  | `A5` | Output | Hardware I2C SCL | DS3231 RTC (`0x68`) and PCF8574 LCD backpack (`0x27`) |
  | `D0` | Serial RX | Hardware UART RX | 9600 baud cross-over from WEMOS D1 Mini TX (GPIO1) |
  | `D1` | Serial TX | Hardware UART TX | 9600 baud cross-over to WEMOS D1 Mini RX (GPIO3) |
  | `D2` | Digital Output | `emergencyGensetPin` | Active-LOW emergency alarm indicator LED and panel fault signal |
  | `D4` | Digital Output | `relay1` | Active-LOW relay contactor: Genset Run / Ignition coil |
  | `D5` | Digital Output | `relay2` | Active-LOW relay contactor: Genset Starter Solenoid |
  | `D7` | Digital Input | `BTN_LEFT` | Active-LOW push button with internal pull-up (LCD menu cycle left) |
  | `D8` | Digital Input | `BTN_RIGHT` | Active-LOW push button with internal pull-up (LCD menu cycle right) |

### 1.2 ATS MQTT Bridge (`firmware/WEMOS_ATS/WEMOS_ATS.ino`)
- **Microcontroller**: Espressif ESP8266EX (Wemos D1 Mini module, 80 MHz default / 160 MHz capable).
- **Memory**: 4 MB SPI Flash (external Winbond), 80 KB internal SRAM (~35 KB free heap).
- **Wireless**: 802.11 b/g/n Wi-Fi, Station mode connecting to hidden SSID `smsb-iot`.
- **Pin Map**:
  | Pin | GPIO | Mode / Type | Connected Component & Function |
  |---|---|---|---|
  | `RX` | GPIO3 | Serial RX | 9600 baud UART RX from Pro Mini TX (Pin D1) |
  | `TX` | GPIO1 | Serial TX | 9600 baud UART TX to Pro Mini RX (Pin D0) |
  | `D1` | GPIO5 | Output | Software I2C SCL for optional SSD1306 OLED display (`0x3C`) |
  | `D2` | GPIO4 | Bidirectional | Software I2C SDA for optional SSD1306 OLED display (`0x3C`) |
  | `D7` | GPIO13 | Digital Output | Debug LED output (driven LOW on startup) |

### 1.3 Temperature / Humidity Sensor Node (`firmware/WEMOS_TS/WEMOS_TS.ino`)
- **Microcontroller**: Espressif ESP8266EX (Wemos D1 Mini).
- **Serial Interface**: 115200 baud UART on USB-UART bridge (diagnostic logging).
- **Pin Map**:
  | Pin | GPIO | Mode / Type | Connected Component & Function |
  |---|---|---|---|
  | `D1` | GPIO5 | Output | Software I2C SCL (SSD1306 OLED + Sensirion SHT30/31) |
  | `D2` | GPIO4 | Bidirectional | Software I2C SDA (SSD1306 OLED + Sensirion SHT30/31) |

### 1.4 Dual AC IR Controller Node (`firmware/WEMOS_AC/WEMOS_AC.ino`)
- **Microcontroller**: Espressif ESP8266EX (Wemos D1 Mini).
- **Serial Interface**: 115200 baud UART (Local interactive CLI + diagnostic logging).
- **Pin Map**:
  | Pin | GPIO | Mode / Type | Connected Component & Function |
  |---|---|---|---|
  | `D1` | GPIO5 | Output | Software I2C SCL (SSD1306 OLED + Sensirion SHT30/31) |
  | `D2` | GPIO4 | Bidirectional | Software I2C SDA (SSD1306 OLED + Sensirion SHT30/31) |
  | `D5` | GPIO14 | Digital Output | `IR1_PIN` (38 kHz modulated IR LED driving Gree AC Unit 1) |
  | `D6` | GPIO12 | Digital Output | `IR2_PIN` (38 kHz modulated IR LED driving Gree AC Unit 2) |

---

## 2. I2C Bus Topology & Peripheral Addressing

All ESP8266 nodes run software I2C initialized via `Wire.begin(D2, D1)` clocked at 100 kHz Standard Mode (`Wire.setClock(100000)`). The ATmega328P runs hardware TWI via `Wire.begin()` on A4/A5 at 100 kHz.

### 2.1 I2C Address Map
| 7-bit Address | Target Peripheral | Node Host | Description |
|---|---|---|---|
| `0x27` | PCF8574 I2C Backpack | PROMINI | LiquidCrystal_I2C 16x2 character display |
| `0x3C` | SSD1306 128x64 OLED | WEMOS_ATS, WEMOS_TS, WEMOS_AC | Primary display address (probed first) |
| `0x3D` | SSD1306 128x64 OLED | WEMOS_TS, WEMOS_AC | Alternate display address (probed second) |
| `0x44` | Sensirion SHT30 / SHT31 | WEMOS_TS, WEMOS_AC | Primary temperature & humidity sensor address (ADDR pin LOW) |
| `0x45` | Sensirion SHT30 / SHT31 | WEMOS_TS, WEMOS_AC | Alternate temperature & humidity sensor address (ADDR pin HIGH) |
| `0x68` | Maxim DS3231 RTC | PROMINI | High-precision battery-backed Real-Time Clock |

### 2.2 Auto-Probing Routine
ESP8266 nodes implement dynamic auto-probing in `scanAndInitI2C()` to guarantee that absent or defective peripherals do not cause boot hangs or software watchdog timeouts:
```cpp
const uint8_t OLED_CANDIDATES[] = {0x3C, 0x3D};
const uint8_t SHT_CANDIDATES[]  = {0x44, 0x45};
```
1. Each candidate address is tested with a dummy write frame (`Wire.beginTransmission(addr); Wire.endTransmission() == 0`).
2. If ACK is received, the peripheral object (`display` or `sht30`) is initialized with that specific address.
3. If no ACK is received, nodes clear presence flags (`isOledPresent = false`, `isShtPresent = false`) and execute headless telemetry loops without blocking.

---

## 3. Non-Volatile Memory (EEPROM) Maps

### 3.1 PROMINI EEPROM Map (ATmega328P Internal EEPROM)
Capacity: 1024 bytes physical EEPROM.
| Byte Offset | Size (Bytes) | Data Type | Identifier | Function / Contract |
|---|---|---|---|---|
| `0x0000`–`0x0003` | 4 | `uint32_t` / `unsigned long` | `nextWarmup` | Unix epoch seconds of next scheduled weekly warmup run |
| `0x0004`–`0x03FF` | 1020 | — | Reserved | Unallocated |

- **Sanity Verification (`loadNextWarmup()`)**:
  - Saved value must satisfy `savedTime > 1700000000UL` (epoch post-November 2023).
  - When RTC is active, `savedTime` must fall within `now - 86400UL` and `now + 8*86400UL`.
  - If corrupted, erased (`0xFFFFFFFF`), or out of range, the FSM calls `getNextWarmup(rtc.now())`, persists the fresh epoch, and logs a recovery frame.
- **Write-Wear Mitigation**: `saveNextWarmup()` executes strictly once per weekly cycle upon warmup completion or initial invalidation.

### 3.2 WEMOS_AC EEPROM Map (ESP8266 Flash Emulation)
Capacity: 32 bytes allocated in SPI flash via `EEPROM.begin(32)`.
| Byte Offset | Size (Bytes) | Field Name | Hex Value / Content | Description |
|---|---|---|---|---|
| `0x00` | 1 | `EEPROM_MAGIC` | `0xAC` | Validity sentinel signature |
| `0x01`–`0x08` | 8 | `AC1_RAW_STATE` | `uint8_t[8]` | Gree 64-bit state frame for AC Unit 1 (`kGreeStateLength`) |
| `0x09`–`0x10` | 8 | `AC2_RAW_STATE` | `uint8_t[8]` | Gree 64-bit state frame for AC Unit 2 (`kGreeStateLength`) |
| `0x11`–`0x1F` | 15 | Reserved | `0x00` | Unallocated padding |

- **Initialization Lifecycle**:
  - If byte `0x00` does not equal `0xAC`, the firmware assumes uninitialized or corrupted sector state.
  - Both AC units default to baseline safe configuration: OFF, Cool Mode, 24°C, Auto Fan.
  - IR commands are transmitted immediately to synchronize physical AC units with baseline state.
  - Byte `0xAC` and raw buffers are written and committed via `EEPROM.commit()`.
- **Commit Guard**: `EEPROM.commit()` writes directly to flash sector memory and is called strictly on discrete user actions (MQTT downlink commands or Serial CLI input), never in continuous loop execution.

---

## 4. Serial Protocol Framing (PROMINI <-> WEMOS_ATS)

The ATmega328P FSM controller and ESP8266 MQTT bridge communicate across hardware UART at 9600 baud, 8 data bits, no parity, 1 stop bit (8-N-1).

### 4.1 Frame Structure & Syntax
Frames are ASCII strings delimited by opening `<` and closing `>` characters:
```
<{COMMAND_OR_KEY},{VALUE}>
```
- **Buffer Safety**: Both nodes parse incoming streams into bounded character arrays `char[65]` (`CMD_BUF_LEN = 64`).
- **Buffer Overflow Protection**: If characters between `<` and `>` exceed 64, the buffer index resets to 0, an internal counter increments, and an error frame `<ERR,overflow,{count}>` is emitted.

### 4.2 Downlink Commands (WEMOS_ATS -> PROMINI)
| Command Frame | Arguments | Description | Guard / Precondition |
|---|---|---|---|
| `<C,GET>` | None | Polls complete state and sensor telemetry | Processed immediately |
| `<M,auto>` | None | Sets ATS mode to Automatic | Transitions `autoMode = true` |
| `<M,manual>` | None | Sets ATS mode to Manual | Transitions `autoMode = false`, resets starter relays |
| `<SGM,on>` | None | Manual start genset crank sequence | Blocked if `autoMode == true` |
| `<SGM,off>` | None | Manual genset shutdown command | Blocked if `autoMode == true` |
| `<RST,rst>` | None | Resets `EMERGENCY_GENSET` lockout latch | Requires exact string token `rst` |
| `<T,{epoch}>` | `uint32_t` | Synchronizes RTC with NTP time | Guarded: `1.7e9 < epoch < 4.1e9` |

### 4.3 Uplink Telemetry Frames (PROMINI -> WEMOS_ATS)
Emitted in response to `<C,GET>`:
| Frame | Data Type | Example | Description |
|---|---|---|---|
| `<STATE,{s}>` | String | `<STATE,PLN>` | Current ATS FSM state name |
| `<PLN,{v}>` | Float | `<PLN,221.40>` | Mains Grid AC RMS Voltage |
| `<GENSET,{v}>` | Float | `<GENSET,0.00>` | Generator AC RMS Voltage |
| `<AKI,{v}>` | Float | `<AKI,12.60>` | Starter Battery DC Voltage |
| `<REM_SEC,{n}>` | Integer | `<REM_SEC,45>` | Warmup countdown remaining seconds |
| `<REM_MIN,{n}>` | Integer | `<REM_MIN,12>` | Warmup countdown remaining minutes |
| `<REM_HOUR,{n}>` | Integer | `<REM_HOUR,2>` | Warmup countdown remaining hours |
| `<AUTO_MODE,{b}>` | Boolean (0/1) | `<AUTO_MODE,1>` | 1 = Automatic Mode, 0 = Manual Mode |
| `<EMERGENCY,{b}>` | Boolean (0/1) | `<EMERGENCY,0>` | 1 = Emergency Latch Active, 0 = Normal |
| `<RTC_OK,{b}>` | Boolean (0/1) | `<RTC_OK,1>` | 1 = DS3231 online, 0 = RTC Offline |

Asynchronous event frames emitted by PROMINI:
- `<RESET_OK,Emergency direset, sistem kembali normal>`: Emitted when emergency latch is cleared by `<RST,rst>`.
- `<SGM blocked autoMode=1>`: Emitted when manual start is requested while in Auto mode.
- `<ERR,overflow,{n}>`: Emitted when serial buffer capacity (64 chars) is exceeded.

---

## 5. ATS Finite State Machine (FSM) Transition Matrix

The ATS controller operates a 13-state deterministic finite state machine governing automatic source transfer, genset cranking, emergency lockout, and maintenance warmup.

```
                      +-----------------------------+
                      |            WAIT             | <====================+
                      +-----------------------------+                      |
                                     | (10s vote)                          |
                                     v                                     |
                      +-----------------------------+                      |
                      |         CHECK_WAIT          |                      |
                      +-----------------------------+                      |
                        /                         \                        |
         PLN Valid     /                           \ PLN Invalid           |
                      v                             v                      |
        +-----------------------+     +---------------------------+        |
        |          PLN          |     |         LONG_WAIT         |        |
        +-----------------------+     +---------------------------+        |
          |           |                            | (30s vote)            |
          | PLN Drop  | Warmup Overdue             v                       |
          v           v               +---------------------------+        |
        [WAIT]   [WAIT_GENSET] <----- |      CHECK_LONG_WAIT      |        |
                      ^               +---------------------------+        |
                      |                                                    |
                      +------------------------------------------+         |
                      |                                          |         |
                      v                                          |         |
        +---------------------------+                            |         |
        |        WAIT_GENSET        |                            |         |
        +---------------------------+                            |         |
                      | (10s vote)                               |         |
                      v                                          |         |
        +---------------------------+                            |         |
        |     CHECK_WAIT_GENSET     |                            |         |
        +---------------------------+                            |         |
          /                       \                              |         |
Genset   /                         \ Genset Off                  |         |
Active  /                           \                            |         |
       v                             v                           |         |
+--------------+           +--------------------+                |         |
|    GENSET    |           |    START_GENSET    |                |         |
+--------------+           +--------------------+                |         |
  |     |                    | (Relay 1 ON)                      |         |
  | PLN | 5 min              | (Relay 2 Crank 2s)                |         |
  | Ret | Warmup Done        v                                   |         |
  v     v                  +--------------------------+          |         |
[LONG_WAIT] [PLN]          | DELAY_AFTER_START_GENSET |          |         |
                           +--------------------------+          |         |
                             | (Wait 20s, attempts++)            |         |
                             v                                   |         |
                           (Attempts >= 3?)                      |         |
                             /          \                        |         |
                       Yes  /            \ No                    |         |
                           v              +----------------------+         |
           +--------------------+                                          |
           |  EMERGENCY_GENSET  | -----------------------------------------+
           +--------------------+            (Manual <RST,rst>)
```

### 5.1 FSM State Transition Matrix
| Current State | Evaluated Condition / Predicate | Next State | Action / Relay Side Effect | Timing / Delay |
|---|---|---|---|---|
| `WAIT` | `indexTegangan < SIZE (20)` | `WAIT` | `dataTegangan[index++] = isPlnOn` | 500 ms cycle |
| `WAIT` | `indexTegangan >= SIZE (20)` | `CHECK_WAIT` | `hasilWait = cariModus(dataTegangan, 20); indexTegangan = 0` | 10 seconds total |
| `CHECK_WAIT` | `hasilWait == true` (PLN valid) | `PLN` | None | Immediate |
| `CHECK_WAIT` | `hasilWait == false` (PLN invalid) | `LONG_WAIT` | None | Immediate |
| `PLN` | `countdown.remSecTotal <= 0` | `WAIT_GENSET` | `matikan_genset(); isWarmup = true; persistNextWarmup()` | Immediate |
| `PLN` | `isAkiOn == false` | `WAIT_AKI` | `matikan_genset()` | Immediate |
| `PLN` | `isPlnOn == false` | `WAIT` | `matikan_genset()` | Immediate |
| `LONG_WAIT` | `indexTegangan < LONG_SIZE (60)` | `LONG_WAIT` | `dataTegangan_long[index++] = isPlnOn` | 500 ms cycle |
| `LONG_WAIT` | `indexTegangan >= LONG_SIZE (60)` | `CHECK_LONG_WAIT` | `hasilWait = cariModus(dataTegangan_long, 60); indexTegangan = 0` | 30 seconds total |
| `CHECK_LONG_WAIT` | `hasilWait == true` (PLN returned) | `PLN` | None | Immediate |
| `CHECK_LONG_WAIT` | `hasilWait == false` (Blackout confirmed) | `WAIT_GENSET` | `waktuGlobal_last2 = waktuGlobal` | Immediate |
| `WAIT_AKI` | `indexTegangan < SIZE (20)` | `WAIT_AKI` | `dataTegangan[index++] = isAkiOn` | 500 ms cycle |
| `WAIT_AKI` | `indexTegangan >= SIZE (20)` | `CHECK_WAIT_AKI` | `hasilWait = cariModus(dataTegangan, 20); indexTegangan = 0` | 10 seconds total |
| `CHECK_WAIT_AKI` | `hasilWait == true` (Battery healthy) | `PLN` | None | Immediate |
| `CHECK_WAIT_AKI` | `hasilWait == false` (Battery degraded) | `WAIT_GENSET` | `isWarmup = true` (Battery maintenance run) | Immediate |
| `WAIT_GENSET` | `indexTegangan < SIZE (20)` | `WAIT_GENSET` | `dataTegangan[index++] = isGensetOn` | 500 ms cycle |
| `WAIT_GENSET` | `indexTegangan >= SIZE (20)` | `CHECK_WAIT_GENSET` | `hasilWait = cariModus(dataTegangan, 20); indexTegangan = 0` | 10 seconds total |
| `CHECK_WAIT_GENSET`| `hasilWait == true` (Genset active) | `GENSET` | `waktuGlobal_last2 = waktuGlobal; relayOrder = 0` | Immediate |
| `CHECK_WAIT_GENSET`| `hasilWait == false && attempts >= 3` | `EMERGENCY_GENSET` | `emergencyNotified = true; matikan_genset(); lepas_starter_genset()` | Immediate |
| `CHECK_WAIT_GENSET`| `hasilWait == false && attempts < 3` | `START_GENSET` | `matikan_genset(); lepas_starter_genset(); relayOrder = 0` | Immediate |
| `START_GENSET` | `relayOrder == 0 && dt >= 3000ms` | `START_GENSET` | `nyalakan_genset(); relayOrder++` (Relay 1 LOW) | 3 seconds |
| `START_GENSET` | `relayOrder == 1 && dt >= 3000ms` | `START_GENSET` | `mulai_starter_genset(); relayOrder++` (Relay 2 LOW) | 3 seconds |
| `START_GENSET` | `relayOrder == 2 && dt >= 2000ms` | `DELAY_AFTER_START_GENSET`| `lepas_starter_genset()` (Relay 2 HIGH) | 2 seconds |
| `DELAY_AFTER_START_GENSET` | `dt >= 20000ms` | `WAIT_GENSET` | `gensetStartAttempts++; waktuGlobal_last2 = waktuGlobal` | 20 seconds |
| `GENSET` | `isGensetOn == false` | `WAIT_GENSET` | None | Immediate |
| `GENSET` | `isWarmup == true && dt >= 300000ms` | `PLN` | `isWarmup = false; warmupStarted = false; saveNextWarmup()` | 5 minutes |
| `GENSET` | `isPlnOn == true && isWarmup == false` | `LONG_WAIT` | Re-transfer confirmation delay | Immediate |
| `EMERGENCY_GENSET`| `emergencyNotified == false` (via `<RST,rst>`) | `WAIT` | `gensetStartAttempts = 0; matikan_lampu_emergency()` | Immediate |
| `EMERGENCY_GENSET`| `emergencyNotified == true` | `EMERGENCY_GENSET`| `nyalakan_lampu_emergency()` (Pin D2 LOW), emit alert | Continuous |

---

## 6. Voltage Hysteresis & Signal Conditioning

To prevent contactor chatter and oscillation during brownouts:
- **AC Mains & Generator Hysteresis**:
  - `VAC_ON = 210.0f` VAC.
  - `VAC_OFF = 190.0f` VAC.
  - Evaluation: `isPlnOn = isPlnOn ? (teganganPln >= VAC_OFF) : (teganganPln >= VAC_ON)`.
- **Battery DC Hysteresis**:
  - `AKI_ON = 12.5f` VDC.
  - `AKI_OFF = 11.5f` VDC.
  - Evaluation: `isAkiOn = isAkiOn ? (teganganAki >= 11.5f) : (teganganAki >= 12.5f)`.
- **Median-of-3 Analog Sampling**:
  - Both `readVAC()` and `readVDC()` take 3 consecutive samples spaced 10 ms apart and return the median value, filtering single-cycle noise spikes.
- **Majority Voting Window (`cariModus`)**:
  - Standard voting: `SIZE = 20` samples (10 seconds).
  - Blackout confirmation voting: `LONG_SIZE = 60` samples (30 seconds).
  - Tie resolution: If true counts equal false counts, the previous state `hasilWait` is preserved.

---

## 7. Safety Systems & Watchdogs

1. **AVR Watchdog Timer (Pro Mini)**:
   - Configured for 8.0-second timeout (`WDTO_8S`).
   - Reset via `wdt_reset()` at loop boundaries, boot delays, and inside `do_lcd()`.
2. **Glitch-Safe Relay Initialization**:
   - ATmega328P pins D2, D4, and D5 are driven `HIGH` via `digitalWrite()` *before* calling `pinMode(pin, OUTPUT)`. This prevents transient active-LOW relay coil activation during reset.
3. **Emergency Disengagement**:
   - Both ignition and starter relays are forced `HIGH` (de-energized) upon entering `EMERGENCY_GENSET`.

---

## 8. Production-Readiness Gap Analysis

### 8.1 I2C Bus Lockup Vulnerability
- **Defect**: No I2C bus clearing sequence is executed prior to calling `Wire.begin()` on either ATmega328P or ESP8266.
- **Failure Mode**: If an MCU reboots during an active read transaction while a slave (e.g. SHT30 or SSD1306) is holding SDA LOW, the hardware I2C controller hangs or reports bus faults indefinitely upon reboot.
- **Remediation**: Implement a 9-clock SCL toggling routine before `Wire.begin()`:
  ```cpp
  pinMode(SDA_PIN, INPUT_PULLUP);
  pinMode(SCL_PIN, OUTPUT);
  for (int i = 0; i < 9; i++) {
      digitalWrite(SCL_PIN, HIGH); delayMicroseconds(5);
      digitalWrite(SCL_PIN, LOW);  delayMicroseconds(5);
  }
  // Generate STOP condition
  ```

### 8.2 Heap Fragmentation & Dynamic String Usage on ESP8266
- **Defect**: While `WEMOS_ATS` uses static buffers, `WEMOS_AC.ino` still uses Arduino `String` in `processSerialCommand()` (`cmd.substring()`, `cmd.trim()`, `cmd.toInt()`) and `mqttClientId`.
- **Failure Mode**: The ESP8266 has limited free heap (~35 KB). Dynamic heap allocations cause fragmentation over extended uptime, culminating in memory allocation failures and soft WDT resets (`rst cause:4`).
- **Remediation**: Replace all dynamic `String` allocations in `WEMOS_AC.ino` with bounded `char[]` arrays and `strchr()`/`strncmp()` tokenization.

### 8.3 Unrecorded Brownout & Watchdog Resets
- **Defect**:
  - `PROMINI.ino` clears `MCUSR = 0` on boot without preserving reset flag bits (`WDRF`, `BORF`, `EXTRF`, `PORF`).
  - ESP8266 nodes do not capture or report `ESP.getResetInfo()` / `ESP.getResetReason()`.
- **Failure Mode**: Field reboots due to brownouts or watchdog timeouts are invisible to telemetry; nodes appear to reboot normally without diagnostic footprints.
- **Remediation**: Save `MCUSR` to a boot variable on the ATmega328P and emit `<BOOT,{mcusr}>` to the bridge. On ESP8266, extract `rst_info.reason` and append `RST_REASON` to telemetry.

### 8.4 Absence of Over-The-Air (OTA) Updating
- **Defect**: Firmware updates require wired physical programming (FTDI serial for Pro Mini, USB serial for Wemos D1 Mini).
- **Failure Mode**: Critical field bugs (such as the August 2026 warmup drift) require physical access to electrical switchgear.
- **Remediation**: Implement authenticated HTTP OTA update capabilities on all ESP8266 nodes, triggered via secure MQTT downlink.

### 8.5 Bench Simulation & HIL Testing Harness
- **Defect**: Zero automated integration or unit tests exist for the Pro Mini FSM.
- **Failure Mode**: Regressions in timing constants, voting filters, or relay sequencing cannot be caught in CI/CD.
- **Remediation**: Implement a Python-based hardware-in-the-loop (HIL) or software-in-the-loop (SIL) test harness that drives the UART protocol and asserts relay states against simulated voltage inputs.
