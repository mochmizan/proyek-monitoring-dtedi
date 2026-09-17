---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-firmware-fleet.md, wiki/concept-edge-resilience.md, wiki/concept-command-path.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-ats-emergency-2026-08.md, wiki/workstream-firmware-proofing.md]
sources: [firmware/PROMINI/PROMINI.ino, firmware/PROMINI/README.md, firmware/WEMOS_ATS/WEMOS_ATS.ino, firmware/WEMOS_ATS/README.md, notes/firmware_toolchain_and_flashing.md, commit:dcfeb84, commit:7bf3098, git:docs/FIRMWARE_ALIGNMENT_REPORT.md (archived), git:docs/FIRMWARE_PROOFING_PLAN_2026-08-31.md (archived)]
updated: 2026-09-16
---

# ATS Firmware Chain

The Automatic Transfer Switch (ATS) subsystem is a dual-MCU hardware architecture designed for high-reliability electrical source switching between Mains Grid (PLN) and an on-site Diesel Generator (GENSET). The design physically separates hard real-time contactor timing from IP network communication.

```
+-------------------------------------------------------------------------------+
|                       PROMINI (Arduino Pro Mini 5V)                           |
|  - Microchip ATmega328P @ 16 MHz, 5V Logic                                    |
|  - Real-Time Contactor FSM & ZMPT101B AC RMS Sensing                          |
|  - Hardware Relays: D4 (Ignition), D5 (Crank), D2 (Emergency LED)             |
|  - Maxim DS3231 RTC & PCF8574 LCD 1602 (I2C: 0x68, 0x27)                     |
|  - Hardware Watchdog: 8.0 Seconds (WDTO_8S)                                   |
+---------------------------------------^---------------------------------------+
                                        |
                 UART Bus: 9600 baud, 8-N-1 (Cross-over TX/RX)
                 Framing: <COMMAND,VALUE> in bounded char[65]
                                        |
+---------------------------------------v---------------------------------------+
|                       WEMOS_ATS (Wemos D1 Mini)                               |
|  - Espressif ESP8266EX @ 80 MHz, 3.3V Logic                                   |
|  - MQTT / Wi-Fi Protocol Bridge to HubBrain V5                                |
|  - Non-blocking Wi-Fi Reconnect & Exponential MQTT Backoff (3s to 30s)        |
|  - Inbound Command Serialization & Outbound JSON Telemetry Packaging         |
+-------------------------------------------------------------------------------+
```

---

## 1. Dual-MCU Partitioning & Hardware Topology

1. **ATS FSM Controller (`firmware/PROMINI/PROMINI.ino`)**:
   - Executes the core finite state machine controlling high-current AC contactor coils.
   - Reads analog signals from two ZMPT101B active AC voltage transformer modules (A1 = PLN, A0 = GENSET) and a DC voltage divider (A2 = AKI 12V starter battery).
   - Manages the DS3231 real-time clock over I2C (`0x68`) and displays local status on a 16x2 LCD (`0x27`).
   - Runs completely autonomously: if the network or bridge MCU crashes, the ATmega328P continues protecting facility power without interruption.
   - **Toolchain & Flashing Invariant**: Target board `Arduino Pro or Pro Mini`, processor **MUST be `ATmega328P (5V, 16 MHz)`** (3.3V corrupts baud rate to 4800). When flashing via FTDI programmer, the TX/RX jumper wires between Pro Mini and Wemos D1 Mini **must be disconnected** to prevent bus contention and upload failure; see [notes/firmware_toolchain_and_flashing.md](../notes/firmware_toolchain_and_flashing.md).
2. **ATS Network Bridge (`firmware/WEMOS_ATS/WEMOS_ATS.ino`)**:
   - Canonical bridge sketch since commit `7bf3098` (absorbed `fixed_wemos_mqtt_raspi/`).
   - Target board: `LOLIN(WEMOS) D1 R2 & mini` (80MHz, 4MB Flash), libraries: `PubSubClient` v2.8.0, `ArduinoJson` **strictly v6.21.5** (v7.x incompatible).
   - Interacts with the local Mosquitto MQTT broker on the Raspberry Pi edge gateway (`192.168.72.242:1883`, credentials `hubadmin`).
   - Subscribes to downlink topic `hs109rs/ats/command` and publishes uplink telemetry to `hs109rs/ats/data`.
   - Polls the Pro Mini over UART using `<C,GET>` every 500 ms when MQTT is connected, throttled to every 2,000 ms when disconnected to avoid serial bus saturation.

---

## 2. Serial Protocol & Frame Exchange Contract

Communication between the two microcontrollers is framed by ASCII delimiters `<` and `>` over hardware UART at 9600 baud (8-N-1). Both MCUs implement bounded `char[65]` buffers (`CMD_BUF_LEN = 64`) with overflow counters to prevent memory corruption.

### 2.1 Downlink Commands (Bridge -> FSM Controller)
| Command Frame | Purpose | Guard / Validation | Pro Mini Response |
|---|---|---|---|
| `<C,GET>` | Request complete telemetry dump | Handled immediately | Bursts all current state & voltage frames |
| `<M,auto>` | Set Automatic mode | None | Sets `autoMode = true` |
| `<M,manual>` | Set Manual mode | None | Sets `autoMode = false`, resets starter relays |
| `<SGM,on>` | Manual Genset Start Crank | Blocked if `autoMode == true` | Initiates manual starter FSM |
| `<SGM,off>` | Manual Genset Shutdown | Blocked if `autoMode == true` | De-energizes ignition relay |
| `<RST,rst>` | Reset Emergency Lockout | Requires exact parameter `rst` | Resets `emergencyNotified = false`, clears attempts |
| `<T,{epoch}>` | Synchronize DS3231 RTC | Guarded: `1.7e9 < epoch < 4.1e9` | Sets RTC clock, sets `rtcAvailable = true` |

### 2.2 Uplink Telemetry Frames (FSM Controller -> Bridge)
Emitted in response to `<C,GET>`:
- `<STATE,{WAIT|CHECK_WAIT|PLN|GENSET|...}>`: Current FSM operational state.
- `<PLN,{float}>`: Mains grid RMS AC voltage (e.g. `<PLN,220.50>`).
- `<GENSET,{float}>`: Generator RMS AC voltage (e.g. `<GENSET,0.00>`).
- `<AKI,{float}>`: Starter battery DC voltage (e.g. `<AKI,12.65>`).
- `<REM_SEC,{long}>`, `<REM_MIN,{long}>`, `<REM_HOUR,{long}>`: Warmup countdown remaining time.
- `<AUTO_MODE,{1|0}>`: 1 = Auto Mode, 0 = Manual Mode.
- `<EMERGENCY,{1|0}>`: 1 = Emergency Latch Active, 0 = Normal.
- `<RTC_OK,{1|0}>`: 1 = DS3231 I2C ACK, 0 = RTC Offline / degraded mode.

---

## 3. Finite State Machine Dynamics & Electrical Safeguards

The Pro Mini FSM implements 13 discrete states governing power transitions:

```
[WAIT] -> [CHECK_WAIT] -> [PLN] (Normal Mains Power)
  |            |            |
  |            +---------> [LONG_WAIT] -> [CHECK_LONG_WAIT] -> [WAIT_GENSET]
  |                                                                |
  +----------------------------------------------------------------+
                                                                   |
                                                                   v
                                                         [CHECK_WAIT_GENSET]
                                                            /           \
                                                    Genset /             \ Genset
                                                   Active /               \ Failed
                                                         v                 v
                                                    [GENSET]         [START_GENSET]
                                                       |                   |
                                                    Warmup                 v
                                                     Done     [DELAY_AFTER_START_GENSET]
                                                       |                   |
                                                       v            (Attempts >= 3?)
                                                     [PLN]          /              \
                                                              Yes   /                \ No
                                                                   v                  v
                                                         [EMERGENCY_GENSET]    [WAIT_GENSET]
```

### 3.1 Voltage Hysteresis & Signal Conditioning
To prevent destructive contactor chatter during electrical brownouts:
- **AC Mains / Genset Hysteresis**:
  - Turn-ON Threshold: `VAC_ON = 210.0f` VAC.
  - Turn-OFF Threshold: `VAC_OFF = 190.0f` VAC.
  - Voltage state evaluation: `isPlnOn = isPlnOn ? (volt >= 190.0f) : (volt >= 210.0f)`.
- **Battery DC Hysteresis**:
  - Healthy Threshold: `AKI_ON = 12.5f` VDC.
  - Low Threshold: `AKI_OFF = 11.5f` VDC.
- **Median-of-3 Analog Sampling**: Every AC reading (`readVAC`) and DC reading (`readVDC`) performs 3 consecutive samples spaced 10 ms apart and returns the median value to reject transient inductive spikes.
- **Debounce Majority Voting (`cariModus`)**:
  - `SIZE = 20` samples (10 seconds) for standard voltage verification.
  - `LONG_SIZE = 60` samples (30 seconds) for mains blackout confirmation (`LONG_WAIT`) before engaging the generator starter.
  - In the event of a tie, the previous voting outcome (`hasilWait`) is preserved.

### 3.2 Starter Crank Cycling & Emergency Lockout
- Staged relay start in `START_GENSET`:
  1. Wait 3 seconds, then energize ignition contactor (`relay1 = LOW`).
  2. Wait 3 seconds, then energize starter motor solenoid (`relay2 = LOW`).
  3. Crank for 2.0 seconds (`STARTER_INTERVAL`), then immediately release starter (`relay2 = HIGH`).
  4. Wait 20 seconds (`DELAY_AFTER_START_GENSET`) for alternator output to stabilize.
- **Maximum Attempt Threshold**: `MAX_START_ATTEMPTS = 3`.
- **Emergency Latch**: If the generator fails to produce valid voltage (`>= 210V`) after 3 attempts, the FSM transitions to `EMERGENCY_GENSET`. Relays 1 and 2 are held HIGH (off), the emergency alarm pin D2 is pulled LOW, and the latch persists indefinitely until cleared by an explicit `<RST,rst>` command.

---

## 4. Timekeeping, Non-Volatile Memory & Warmup

- **DS3231 Real-Time Clock**: Interfaced over I2C at address `0x68`. If RTC initialization fails on boot, `rtcAvailable` is set to `false`, the FSM logs a degraded mode message, and `getWarmupCountdown()` returns `{0,0,0,0}` without halting the system.
- **EEPROM Next Warmup Storage**: Byte address `0x0000` on the ATmega328P stores the 4-byte Unix timestamp of the next scheduled Sunday 18:00 WIB exercise run.
- **EEPROM Sanity Validation**: The stored timestamp is verified on boot (`loadNextWarmup()`). It must be greater than `1700000000UL` and within `now - 1 day` to `now + 8 days`. If invalid, it is recalculated and rewritten.
- **Warmup Runtime**: When triggered, the generator runs for 5 minutes (`FIVE_MIN = 300000ms`) in state `GENSET` with contactors safely holding facility load on PLN. Upon completion, the next week's schedule is committed to EEPROM.

---

## 5. Production-Readiness Gap Analysis

A rigorous engineering review identifies six critical gaps preventing enterprise production sign-off:

### 5.1 Uncaptured Watchdog & Brownout Resets
- **Defect**: `PROMINI.ino` line 160 executes `MCUSR = 0; wdt_disable();` without saving the `MCUSR` register.
- **Impact**: It is impossible to determine whether an ATmega328P reboot was caused by an 8-second watchdog timeout (`WDRF`), an electrical brownout (`BORF`), or an external reset pin pulse (`EXTRF`). Telemetry cannot report reboot causes.
- **Remediation**: Save `MCUSR` to a global variable before clearing, and transmit a `<BOOT,{mcusr}>` frame to the bridge on startup.

### 5.2 Missing I2C Bus Unjamming Routine
- **Defect**: Neither Pro Mini nor WEMOS_ATS implements an I2C clock-pulsing clear sequence.
- **Impact**: If a brownout occurs while the DS3231 RTC or LCD is asserting ACK (pulling SDA low), the hardware TWI peripheral locks up upon restart.
- **Remediation**: Implement a 9-pulse SCL toggle sequence before calling `Wire.begin()`.

### 5.3 Lack of ESP8266 Reset Reason Reporting
- **Defect**: `WEMOS_ATS.ino` does not read `ESP.getResetInfo()` or `ESP.getResetReason()`.
- **Impact**: If the ESP8266 reboots due to Wi-Fi stack panic or software watchdog, the central server receives no diagnostic indicators.
- **Remediation**: Append `RST_REASON` and `FREE_HEAP` to the outbound JSON payload on `hs109rs/ats/data`.

### 5.4 Zero Over-The-Air (OTA) Updating
- **Defect**: Field firmware cannot be updated over the network.
- **Impact**: During the August 2026 emergency, software fixes required physical access to the electrical switchboard.
- **Remediation**: Implement an authenticated HTTP OTA client or `ArduinoOTA` listener on `WEMOS_ATS`.

### 5.5 Absence of Automated Simulation & HIL Testing Harness
- **Defect**: Zero automated integration or unit tests exist for the Pro Mini FSM.
- **Impact**: Timing regressions, voting logic errors, or relay race conditions cannot be tested in CI/CD without physical hardware.
- **Remediation**: Implement a Python-based software-in-the-loop (SIL) or hardware-in-the-loop (HIL) test harness to simulate UART stimuli and assert contactor responses.

### 5.6 Field Fleet Deployment Status
- As of 2026-09-03, field unit `68:C6:3A:D7:60:47` (HS109SR-ATS) still runs pre-proofed firmware.
- The emergency is currently contained purely via server-side auto-resolve logic (`alert_engine.py` auto-resolving `EMERGENCY=1` when `PLN > 210V && GENSET < 80V`).
- Physical flashing of proofed `firmware/PROMINI/PROMINI.ino` and `firmware/WEMOS_ATS/WEMOS_ATS.ino` remains a critical operational prerequisite.
