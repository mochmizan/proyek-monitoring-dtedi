# Runbook: Field Node ATS Remediation & Firmware Flashing

**Target Node**: `68:C6:3A:D7:60:47` (HS109SR-ATS / Switchboard ATS Unit)  
**Location**: Switchboard / Genset Room, Gedung DTEDI SV UGM  
**Severity**: High (Emergency Alarm Latch / Hardware Sensing Anomaly)  
**Classification**: Electrical & Firmware Field Remediation  
**Status**: Ready for On-Site Execution  

---

## 1. Incident Summary & Root Cause Analysis

### 1.1 Problem Symptoms
Field ATS telemetry node `68:C6:3A:D7:60:47` exhibited recurring critical alarms in the HubGate V5 monitoring platform:
1. Continuous `EMERGENCY_GENSET` (`EMERGENCY=1`) state latched in telemetry packets sent to topic `hs109rs/ats/data`.
2. Generator sensing voltage reporting approximately **~55V AC floating** when the generator was completely powered off.
3. Issuing a remote software reset (`<RST>`) or power-cycling the node caused an immediate reboot, followed by repetitive generator start attempts (starter relay pulsing), eventual retry exhaustion, and immediate re-latching of `EMERGENCY_GENSET` (the **Reset Loop**).

### 1.2 Root Cause Diagnosis
The failure represents an interaction between an electrical hardware defect and pre-proofed firmware logic:

```
[Electrical Anomaly]
Genset Voltage Sensing Wire Disconnected / Open Circuit
         │
         ▼
High-impedance ZMPT101B transformer input picks up capacitive & inductive
coupling from adjacent 220V/380V lines --> ~55V AC floating phantom reading
         │
         ▼
[Firmware Anomaly: Pre-proofed PROMINI]
1. Internal warmup timer drifted (Sunday 18:00 WIB drifted to 11:11 WIB due to no RTC sync)
2. On boot or timer expiration, firmware initiates autonomous warmup sequence
3. Firmware pulses starter relay, waits for generator voltage > 200V
4. Sensing reads only ~55V floating (< 200V threshold)
5. Starter retries exhaust MAX attempts (5)
6. State machine latches into EMERGENCY_GENSET
         │
         ▼
[The Reset Loop Trap]
Reboot / <RST> command clears RAM, but does NOT clear the condition:
Timer is still overdue + sensing still reads ~55V floating
--> Immediately re-executes start attempts --> Re-latches EMERGENCY_GENSET!
```

### 1.3 Server-Side Temporary Mitigation vs Permanent Fix
- **Server Mitigation (Commit `a4a6769`)**: `alert_engine.py` was patched to suppress emergency alarms when `PLN > 210V && GENSET < 80V`. This prevented alarm floods across the dashboard.
- **Permanent Solution Required**: 
  1. Reconnect/terminate the physical generator voltage sensing wire to restore accurate 0V readings when stopped.
  2. Flash canonical `firmware/PROMINI/PROMINI.ino` (removes autonomous warmup, enforces PLN-priority FSM, caps retries to 3, initializes relays HIGH).
  3. Flash canonical `firmware/WEMOS_ATS/WEMOS_ATS.ino` (non-blocking Wi-Fi/MQTT, publish throttling, bounded buffers).

---

## 2. Safety, PPE & Isolation Procedures

> [!CAUTION]
> The ATS enclosure contains live 220V / 380V 3-phase AC busbars from PLN mains and the generator. Arc flash and lethal electric shock hazards are present. Only authorized electrical maintenance personnel may open the enclosure.

### Required Personal Protective Equipment (PPE)
- Insulating gloves rated for Class 0 (1,000V AC).
- Safety glasses or full-face arc shield.
- Flame-resistant (FR) protective clothing.
- Closed-toe dielectric safety footwear.

### Pre-Work Electrical Isolation Checklist
1. **Lock-Out / Tag-Out (LOTO)**:
   - If work requires contacting primary terminal blocks, open the upstream mains circuit breaker feeding the ATS sensing inputs and apply a padlock/tag.
   - Set the generator control panel switch to **OFF / MANUAL** (disable remote auto-start) and disconnect the 12V/24V generator starter battery positive terminal to prevent accidental engine crank during maintenance.
2. **Zero Energy Verification**:
   - Using a certified CAT III / CAT IV 600V digital multimeter, verify 0.0V AC phase-to-phase and phase-to-neutral across the sensing lines before touching conductors.

---

## 3. Physical Hardware Remediation

### 3.1 Terminal Block Inspection & Wire Reconnection
1. Open the ATS control cabinet door and locate the sensor interface PCB (containing the two blue ZMPT101B voltage transformer modules).
2. Trace the high-voltage input leads connected to the **GENSET ZMPT101B** sensor module:
   - Identify terminal block `TB_GEN_L` (Phase) and `TB_GEN_N` (Neutral).
   - Locate the disconnected or loose wire originating from the generator output auxiliary breaker or sensing potential transformer.
3. Inspect wire condition:
   - Check for loose screw terminals, broken copper strands, or cold solder joints on the screw terminals.
   - Strip wire cleanly by 8mm, crimp an insulated ferrule (bootlace ferrule), and insert firmly into the terminal block.
   - Torque terminal screw to manufacturer specification (typically 0.5–0.6 N·m).

### 3.2 Floating Voltage Elimination & Verification
To guarantee that high-impedance floating pickup is completely eliminated when the generator is off:
- If high-impedance capacitive pickup is observed (> 10V AC induced on open circuit), attach a high-wattage bleeder resistor network (e.g., 220kΩ 2W metal oxide resistor across `TB_GEN_L` and `TB_GEN_N`) to bleed off capacitive coupling without creating significant parasitic load.
- **Multimeter Verification**:
  1. With Generator OFF and PLN ON: Measure AC voltage at `TB_GEN_L` to `TB_GEN_N`.
     - **Required Reading**: $0.0\text{V} \pm 2.0\text{V AC}$ (Must NOT read ~55V).
  2. With Generator manually running: Measure AC voltage at `TB_GEN_L` to `TB_GEN_N`.
     - **Required Reading**: $220\text{V} \pm 10\text{V AC}$ (Phase-Neutral) or nominal system voltage.

---

## 4. Firmware Proofing Remediation

### 4.1 Changes in Canonical `PROMINI.ino`
The canonical sketch at [`firmware/PROMINI/PROMINI.ino`](file:///c:/Users/Mizan/Documents/smsb/firmware/PROMINI/PROMINI.ino) eliminates the root causes of the emergency reset loop:
- **Autonomous Warmup Removed**: All scheduled autonomous warmup logic has been removed. Warmup cannot be initiated by the device itself; it only runs when commanded via `<SGM>` and autoMode is enabled.
- **PLN-Priority FSM**: Contactor stays locked to PLN as long as PLN voltage exceeds the 210V threshold (with median filtering across 20–60 samples to reject transients).
- **Reduced Starter Retries**: Maximum crank attempts reduced from 5 to 3 (`BATAS_PERCOBAAN_STARTER 3`).
- **Relay Pin Glitch Prevention**: Contactor and starter relay pins are set to `HIGH` (active-LOW relays off) *before* configuring them as `OUTPUT`, preventing spurious relay clicks upon boot.
- **Hardware Watchdog & Diagnostics**: 8-second AVR Watchdog Timer (`wdt_enable(WDTO_8S)`) with `MCUSR` capture and boot frame transmission (`<BOOT,{mcusr}>`).
- **Bounded Serial Protocol**: Fixed `char[65]` buffer prevents stack/heap corruption from noisy serial lines.

### 4.2 Changes in Canonical `WEMOS_ATS.ino`
The canonical sketch at [`firmware/WEMOS_ATS/WEMOS_ATS.ino`](file:///c:/Users/Mizan/Documents/smsb/firmware/WEMOS_ATS/WEMOS_ATS.ino):
- **Non-Blocking Connectivity**: Uses non-blocking Wi-Fi and MQTT reconnection loops with exponential backoff (3s–30s), eliminating CPU lockups during network hiccups.
- **Throttled Telemetry**: Enforces 500ms minimum interval between updates and 2000ms periodic heartbeat to prevent network congestion.
- **Diagnostic Telemetry**: Appends reset reason and free heap metrics to MQTT messages.

---

## 5. Step-by-Step On-Site Serial Flashing Procedure

### 5.1 Tooling & Prerequisites
- Laptop with Python 3, `pip`, and USB drivers installed.
- **PlatformIO Core** (`pip install platformio`) OR **arduino-cli**.
- **USB-to-UART Serial Adapter (FTDI FT232RL or CP2102)**: Must support 5V VCC and include a **DTR** pin for hardware auto-reset on the Pro Mini.
- **Micro-USB Data Cable** for the Wemos D1 Mini.
- Clone of the `proyek-monitoring-dtedi` repository (`smsb`).

### 5.2 Flash 1: ATmega328P Arduino Pro Mini (5V, 16MHz)

> [!IMPORTANT]
> The hardware UART lines (pins TX/RX) between the Pro Mini and Wemos D1 Mini are bridged for operational communication. You **MUST** temporarily disconnect the jumper wires connecting Pro Mini TX/RX to Wemos D1 Mini before connecting the FTDI programmer to avoid serial bus contention.

#### Pin Connections (FTDI Programmer to Pro Mini)
| FTDI Adapter Pin | Pro Mini Pin | Description |
| :--- | :--- | :--- |
| **GND** | **GND** (or BLK) | Ground Reference |
| **VCC** | **VCC** (5V) | 5V Power Supply |
| **RXD** | **TXO** (Pin 1) | Pro Mini Transmit -> Programmer Receive |
| **TXD** | **RXI** (Pin 0) | Programmer Transmit -> Pro Mini Receive |
| **DTR** | **DTR** (or GRN) | Hardware Reset Line (Required for bootloader) |

#### Flashing via `arduino-cli`:
```bash
cd /path/to/smsb/firmware/PROMINI

# 1. Install AVR core if not present
arduino-cli core install arduino:avr

# 2. Compile sketch
arduino-cli compile --fqbn arduino:avr:pro:cpu=16MHzatmega328 PROMINI.ino

# 3. Identify serial port (e.g. /dev/ttyUSB0 or COM3)
arduino-cli board list

# 4. Upload to Pro Mini
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:pro:cpu=16MHzatmega328 PROMINI.ino
```

#### Flashing via `avrdude` directly:
```bash
avrdude -v -p atmega328p -c arduino -P /dev/ttyUSB0 -b 57600 -D \
  -U flash:w:/path/to/compiled/PROMINI.ino.hex:i
```

---

### 5.3 Flash 2: Wemos D1 Mini (ESP8266)

#### Preparation:
Ensure `firmware/common/secrets.h` is present and populated with on-site Wi-Fi and MQTT credentials:
```bash
cd /path/to/smsb/firmware
cp common/secrets.h.example common/secrets.h
nano common/secrets.h
```
Confirm:
```c
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define MQTT_HOST "100.108.98.30" // Production Hub / Tailscale IP
#define MQTT_USER "smsb_edge"
#define MQTT_PASS "your_edge_password"
```

#### Flashing via PlatformIO:
Connect the Wemos D1 Mini directly to your laptop via Micro-USB:
```bash
cd /path/to/smsb/firmware

# Compile and upload Wemos ATS environment
pio run -e wemos_ats -t upload --upload-port /dev/ttyUSB1
```

#### Flashing via `arduino-cli`:
```bash
cd /path/to/smsb/firmware/WEMOS_ATS

# Compile for ESP8266 D1 Mini
arduino-cli compile --fqbn esp8266:esp8266:d1_mini WEMOS_ATS.ino

# Upload
arduino-cli upload -p /dev/ttyUSB1 --fqbn esp8266:esp8266:d1_mini WEMOS_ATS.ino
```

---

### 5.4 Reconnecting Inter-Board Serial Bridge
1. Disconnect the FTDI programmer and Micro-USB cable.
2. Reconnect the hardware serial bridge between the two microcontrollers:
   - `Pro Mini TXO` (Pin 1) $\longrightarrow$ `Wemos D1 Mini RX` (GPIO3).
   - `Pro Mini RXI` (Pin 0) $\longrightarrow$ `Wemos D1 Mini TX` (GPIO1).
   - Ensure common **GND** between Pro Mini and Wemos D1 Mini.
3. Power the system using the cabinet's internal 5V regulated DC supply.

---

## 6. Post-Remediation Verification & Telemetry Validation

### 6.1 Local Serial Console Verification (115200 Baud)
Open a serial terminal connected to the Wemos D1 Mini at `115200 baud`:
```
[BOOT] WEMOS ATS Initializing...
[WiFi] Connected to SSID: ... IP: 192.168.x.x
[MQTT] Connected to broker: 100.108.98.30:1883
[UART] Received from Pro Mini: <BOOT,0>
[UART] Pro Mini state: WAIT_PLN
[STATUS] PLN: 224.2V, GEN: 0.0V, EMERGENCY: 0
```
- Confirm `GEN: 0.0V` (no floating 55V).
- Confirm `EMERGENCY: 0`.

### 6.2 MQTT Live Stream Verification
From a machine on the local network or production server:
```bash
mosquitto_sub -h 127.0.0.1 -t "hs109rs/ats/data" -v
```
Sample verified payload:
```json
{
  "dev_id": "68:C6:3A:D7:60:47",
  "dev_type": "ATS",
  "tegangan_pln": 224.5,
  "tegangan_genset": 0.0,
  "emergency": 0,
  "status_kontaktor": "PLN",
  "mode": "MANUAL",
  "timestamp": "2026-09-12T10:50:00Z"
}
```

### 6.3 Central API & Active Alerts Check
Run these checks against the HubGate V5 API:

```bash
# 1. Check latest telemetry reading for node
curl -sk https://127.0.0.1/api/ats/latest?dev_id=68:C6:3A:D7:60:47 | jq .

# 2. Check active alerts - must be 0 for this node
curl -sk https://127.0.0.1/api/alerts/active | jq '.[] | select(.dev_id=="68:C6:3A:D7:60:47")'
```
Expected output: No active alerts returned for `68:C6:3A:D7:60:47`.

### 6.4 Reboot Stress Test
1. Press the reset button on the Pro Mini / Wemos module or cycle main 5V power.
2. Verify that upon booting, the starter relay does **NOT** click, the generator does **NOT** attempt to crank, and `emergency` remains `0`.
3. The reset loop is permanently resolved.
