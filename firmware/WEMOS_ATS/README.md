# WEMOS_ATS — Deprecated Alias

> **Deprecated fork.** Canonical ATS bridge is [`firmware/fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino`](../fixed_wemos_mqtt_raspi/fixed_wemos_mqtt_raspi.ino).

`WEMOS_ATS/WEMOS_ATS.ino` is a 12-line shim retained only to satisfy the Arduino IDE folder-name requirement. All fixes, fleet AP, and `secrets.h` changes must be made in `fixed_wemos_mqtt_raspi/` — do not maintain two copies.

- `just firmware-check` compiles the 3 canonical ESP dirs (TS, AC, fixed) and skips this alias.
- See `docs/FIRMWARE_ALIGNMENT_REPORT.md` Component 5 for history.
