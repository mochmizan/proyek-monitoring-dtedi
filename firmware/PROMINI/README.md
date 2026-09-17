# PROMINI — Canonical ATS Finite State Machine Firmware

Canonical firmware for the ATmega328P Arduino Pro Mini managing the Automatic Transfer Switch (ATS) FSM, contactor interlocks, ZMPT101B voltage sensing, and starter relay sequences.

## Board Requirements (Arduino IDE)
- **Board**: `Arduino Pro or Pro Mini`
- **Processor**: `ATmega328P (5V, 16 MHz)`
  > **CRITICAL**: The processor selection MUST be **5V, 16 MHz** (NOT 3.3V 8MHz, NOT ATmega168). A mismatched clock rate alters hardware timers and baud rates, preventing UART communication with WEMOS_ATS!
- **Port**: Select the FTDI / USB-to-UART serial adapter COM / tty port.
- **Programmer**: `AVRISP mkII` (default)

## Required Libraries (Library Manager)
1. `ZMPT101B` by Abdurrahman Gök
2. `LiquidCrystal I2C` by Frank de Brabander
3. `RTClib` by Adafruit
4. Built-in AVR libraries (included with Arduino AVR Boards core): `Wire`, `EEPROM`, `avr/wdt.h`

## Flashing Instructions (FTDI Adapter)
> **IMPORTANT**: The hardware UART (pins TX/RX) is bridged to the Wemos D1 Mini. **Temporarily disconnect** the TX/RX jumper wires between Pro Mini and Wemos D1 Mini before connecting the FTDI programmer to avoid serial bus contention during upload.

### Pin Connections (FTDI to Pro Mini):
- FTDI GND -> Pro Mini GND
- FTDI VCC -> Pro Mini VCC (5V)
- FTDI RXD -> Pro Mini TXO (Pin 1)
- FTDI TXD -> Pro Mini RXI (Pin 0)
- FTDI DTR -> Pro Mini DTR (GRN) — for hardware auto-reset
