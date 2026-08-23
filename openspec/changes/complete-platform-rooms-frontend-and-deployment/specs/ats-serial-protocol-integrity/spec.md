## Purpose

Ensures the ATS Wemos bridge and the Arduino FSM controller agree on a single serial command format, resolving a conflict between two differing accounts of that format found earlier in this project.

## ADDED Requirements

### Requirement: A single canonical serial command format is used on both sides
The ATS Wemos bridge and the Arduino FSM controller SHALL use the hardware team's originally specified serial command format — `<SGM,on>`, `<SGM,off>`, `<RST,rst>`, `<M,auto>`, `<M,manual>` — as the canonical protocol. Any code found using a different format for the same commands SHALL be corrected to match this canonical form, rather than the canonical form being changed to match whatever the code happens to do.

#### Scenario: Wemos sends a manual genset start command
- **WHEN** the Wemos bridge sends a manual genset-start command to the Arduino over serial
- **THEN** it transmits exactly `<SGM,on>`

#### Scenario: Wemos sends a reset command
- **WHEN** the Wemos bridge sends a reset command to the Arduino over serial
- **THEN** it transmits exactly `<RST,rst>`

### Requirement: The mismatch is resolved by direct code inspection, not by report summary
Before this requirement is considered satisfied, both `fixed_wemos_mqtt_raspi.ino`'s command-sending code and `fsm_w_serial.ino`'s serial command parser SHALL be read directly and compared against the canonical format above — not inferred from a prior summary document, since a prior summary covering this same protocol was separately confirmed to contain fabricated content elsewhere in this project.

#### Scenario: Discrepancy found during inspection
- **WHEN** direct inspection finds either file using a format other than the canonical one (for example `<C,SGM_ON>` instead of `<SGM,on>`)
- **THEN** that file is corrected to the canonical format, and the correction is verified by an actual bench test (send the command, confirm the expected physical/serial behavior), not just a code review
