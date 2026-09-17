# Firmware Toolchain Invariants & Hardware Flashing Protocol

Notes on firmware build constraints, Arduino IDE 2.x sandbox behavior, library compatibility, and hardware flashing procedures across the fleet (`firmware/PROMINI`, `firmware/WEMOS_ATS`, `firmware/WEMOS_TS`, `firmware/WEMOS_AC`).

## 1. Arduino IDE 2.x Build Sandbox & secrets.h Resolution

- **Root Cause**: Arduino IDE 2.x builds sketches inside an isolated temporary directory (e.g. `/tmp/arduino/sketches/...` or `%TEMP%`). Relative preprocessor paths like `#include "../common/secrets.h"` fail to resolve because the sandbox directory structure does not mirror monorepo parent folders.
- **Remediation & Invariant**:
  - Inverted `#include` priority in all sketches:
    ```cpp
    #if __has_include("secrets.h")
    #include "secrets.h"
    #elif __has_include("../common/secrets.h")
    #include "../common/secrets.h"
    #elif __has_include("common/secrets.h")
    #include "common/secrets.h"
    #else
    #error "secrets.h missing. Ensure secrets.h exists in this sketch folder or in firmware/common/."
    #endif
    ```
  - Sketch-local `secrets.h` files are placed directly in each sketch folder (`firmware/WEMOS_ATS/secrets.h`, `firmware/WEMOS_TS/secrets.h`, `firmware/WEMOS_AC/secrets.h`) and tracked in git with verified campus fleet credentials (`smsb-iot` / `192.168.72.242:1883`) so sketches compile out-of-the-box in Arduino IDE without manual copying.
  - `firmware/common/secrets.h` is retained and tracked as fallback for CLI and multi-sketch builds (`secrets.h.example` retained for reference).

## 2. Board & Toolchain Configurations

### WEMOS_ATS / WEMOS_TS / WEMOS_AC (ESP8266)
- **Board**: `LOLIN(WEMOS) D1 R2 & mini` (ESP8266 Boards core)
- **CPU Frequency**: `80 MHz`
- **Flash Size**: `4MB (FS: 2MB OTA:~1019KB)`
- **Port**: USB Serial port (CH340 / CP2102 onboard)
- **Required Libraries**:
  - `PubSubClient` (v2.8.0 by Nick O'Leary)
  - `ArduinoJson` (**MUST be v6.21.5** — DO NOT upgrade to v7.x; v7 introduces breaking API changes to `StaticJsonDocument` / `DynamicJsonDocument` allocations and JSON serialization methods)
  - `Adafruit SSD1306` & `Adafruit GFX Library`
  - `Adafruit SHT31` (for `WEMOS_TS` and `WEMOS_AC`)
  - `IRremoteESP8266` (for `WEMOS_AC`)

### PROMINI (ATmega328P ATS Finite State Machine)
- **Board**: `Arduino Pro or Pro Mini`
- **Processor**: **`ATmega328P (5V, 16 MHz)`**
  - **CRITICAL**: Do NOT select `3.3V, 8 MHz` or `ATmega168`. Selecting 3.3V/8MHz cuts hardware timer clocks in half and corrupts UART baud rate calculation from 9600 to 4800 baud, completely breaking bidirectional serial framing (`<STATE,...>`, `<C,GET>`) with WEMOS_ATS.
- **Programmer**: `AVRISP mkII` (default)
- **Required Libraries**:
  - `ZMPT101B` by Abdurrahman Gök
  - `LiquidCrystal I2C` by Frank de Brabander
  - `RTClib` by Adafruit
  - Built-in AVR: `Wire`, `EEPROM`, `avr/wdt.h`

## 3. Flashing Caution & UART Contention Prevention

- **Bus Contention Pitfall**: The hardware UART pins between Pro Mini (Pin 1 TXO, Pin 0 RXI) and Wemos D1 Mini (GPIO1 TX, GPIO3 RX) are bridged in hardware for runtime FSM telemetry.
- **Failure Symptom**: Connecting an FTDI USB-UART adapter to the Pro Mini while TX/RX jumpers remain connected causes serial line fighting, resulting in upload failure (`avrdude: stk500_recv(): programmer is not responding` / `not in sync: resp=0x00`).
- **Required Procedure**:
  1. **MUST disconnect** the TX and RX jumper wires between Pro Mini and Wemos D1 Mini before connecting the FTDI programmer.
  2. Connect FTDI to Pro Mini:
     - FTDI GND -> Pro Mini GND
     - FTDI VCC -> Pro Mini VCC (5V)
     - FTDI RXD -> Pro Mini TXO (Pin 1)
     - FTDI TXD -> Pro Mini RXI (Pin 0)
     - FTDI DTR -> Pro Mini DTR (GRN) — enables hardware auto-reset
  3. Flash Pro Mini via Arduino IDE / avrdude.
  4. Flash Wemos D1 Mini separately via its onboard micro-USB port.
  5. Disconnect FTDI programmer and **reconnect** the TX/RX jumper wires between Pro Mini and Wemos D1 Mini before restoring operational power.

## 4. Phase 3 Telemetry Cadence & Deadband Specifications

All ESP8266 nodes implement local Report-by-Exception (RBE) deadbands and decoupled heartbeat publishing:
- **WEMOS_TS**: 300s steady heartbeat, 5s rate-limit, 2s SHT30 sampling, 1 Hz OLED display refresh, $\Delta T \ge 0.2^\circ\text{C}$, $\Delta\text{RH} \ge 2.0\%$, force publish on sensor error / recovery.
- **WEMOS_ATS**: 60s steady heartbeat, 500ms decoupled Pro Mini polling, dynamic burst mode (2.0s cadence for 60s) with instant 0ms forward on discrete state changes (`nowState`, `autoMode`, `emergency`, `pln_relay`, `gen_relay`, `alarm`), electrical deadbands ($\Delta V_\text{PLN} \ge 1.0\text{V}$, $\Delta V_\text{GEN} \ge 1.0\text{V}$, $\Delta V_\text{AKI} \ge 0.1\text{V}$), 2s rate-limit, static bounded buffer safety (`char[512]`, `char[65]`).
- **WEMOS_AC**: 120s steady heartbeat, instant publish on AC downlink/serial command execution (0ms ACK), $\Delta T \ge 0.5^\circ\text{C}$, $\Delta\text{RH} \ge 2.0\%$, 5s rate-limit, 2s sensor sampling, 1 Hz OLED.
- **Verification**: Run `python tools/verify_firmware.py` to assert syntax, compilation guards, timing constants, and PROMINI canonical status.

