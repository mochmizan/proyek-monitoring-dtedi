---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-command-path.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-ats-emergency-2026-08.md, wiki/workstream-firmware-proofing.md]
sources: [firmware/PROMINI/PROMINI.ino, firmware/WEMOS_ATS/WEMOS_ATS.ino, docs/FIRMWARE_ALIGNMENT_REPORT.md, commit:dcfeb84, commit:7bf3098]
updated: 2026-08-31
---

# ATS firmware chain

The automatic transfer switch is a two-MCU pair. **PROMINI** (Arduino Pro Mini) is the FSM that actually switches PLN/genset contactors and reads voltages; **WEMOS_ATS** (ESP8266, WEMOS D1 mini) bridges it to MQTT: it parses serial frames from the Pro Mini, publishes ATS telemetry (PLN/GENSET/AKI volts, STATE, EMERGENCY, AUTO_MODE), and forwards server commands down as serial frames.

Canonical serial framing (both directions): `<SGM,on>` start genset, `<RST,rst>` reset FSM, `<M,auto>` mode, `<T,unixtime>` clock sync (answered with `RTC_OK`). Bounded `char[65]` buffers, 512-byte UART ring.

`firmware/WEMOS_ATS/WEMOS_ATS.ino` has been the canonical bridge since 7bf3098 (2026-08-31) — it absorbed the former `fixed_wemos_mqtt_raspi/` sketch (non-blocking WiFi retry 3s→30s, SGM guarded by autoMode, snprintf clientId, publish-only-while-connected, RTC_OK passthrough). The proofed PROMINI (dcfeb84) carries WDT 8S + MCUSR capture, VAC 210/190 hysteresis with median voting (window SIZE 20, LONG 60), genset start attempts MAX 3, EEPROM sanity guard, and `WARMUP` autonomous start disabled — warmup is server-scheduled now (see [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md)).

Archived sketches: `firmware/archive/fsm_w_serial-2026-08-31/` (bench FSM, daily warmup) and `firmware/bench/HARDWARE_OLED_TEST/` (I2C utility). Neither is deployed. Field units still ran pre-dcfeb84 firmware as of 2026-08-31 (see [workstream-ats-emergency-2026-08.md](workstream-ats-emergency-2026-08.md)).
