# AGENTS.md — openspec (Spec-Driven Change Proposals)

OpenSpec-style spec-driven development workspace. Change proposals live under `changes/<change-name>/`, each describing why, what, capabilities (specs), design decisions, tasks, and impact — with machine-readable requirements per capability.

## Ownership

- **openspec/**: change proposals, capability specs, design/task docs
- Owned by root AGENTS.md for repo-wide rules and the DOX framework
- Proposals are planning artifacts — they may reference code in `clients/`, `SERVERv5/`, `HUBV5/`, and `firmware/` sketch folders

## Structure of a Change

```
changes/<change-name>/
├── .openspec.yaml          ← schema: spec-driven, created date
├── proposal.md             ← Why / What Changes / Capabilities / Impact
├── design.md               ← Context, Goals/Non-Goals, Decisions, Risks, Migration Plan
├── tasks.md                ← Checkbox task list (verification included)
└── specs/
    └── <capability-name>/
        └── spec.md         ← Requirements: SHALL statements + WHEN/THEN scenarios
```

## Changes Index

### 1. `align-field-firmware-with-live-hub`
- **Scope**: Firmware only — ATS bridge alignment (topic/IP/fields), non-blocking peripheral init + MQTT reconnect across all three ESP8266 nodes, AC state persistence via EEPROM
- **Specs**: `ats-node-hub-alignment`, `field-node-connection-resilience`, `ac-node-state-persistence`
- **Status**: **IMPLEMENTED & VERIFIED** (Tasks 1.1–4.4 completed; Section 5 bench tests defined for hardware staging)
- **Reference Doc**: [`FIRMWARE_ALIGNMENT_REPORT.md`](../FIRMWARE_ALIGNMENT_REPORT.md)
- Ground-truth alignment: live hub config (`hs109rs-hub-01`, broker `192.168.72.242`), unified `hs109rs/#` topic tree, `HUB_NAME` / `DEV_TYPE: "ATS"` payload, non-blocking I2C probes (`0x3C`, `0x44`), EEPROM `0xAC` raw state persistence.

### 2. `complete-platform-rooms-frontend-and-deployment`
- **Scope**: Full Platform — Database additive migrations, Rooms & Device Pairing API, Floor Plan Disk Storage & Map API, Alert Engine (debounce & hysteresis), Firmware NaN skip & canonical ATS serial protocol, Edge SQLite WAL cache & dynamic topic dispatch, React SPA live TanStack Query & auth wiring, Docker local test stack, Raspberry Pi backup gate, and production Nginx same-origin deployment.
- **Specs**: `room-and-device-management`, `floor-plan-mapping`, `alert-threshold-evaluation`, `frontend-live-integration`, `edge-offline-resilience`, `local-test-environment`, `production-deployment`, `ats-serial-protocol-integrity`
- **Status**: **IMPLEMENTED & VERIFIED** (All 10 Milestones, Tasks 1.1–13.6 completed; 100 automated tests passing, 0 linter errors, clean SPA build)
- **Reference Docs**: [`LOCAL_TESTING_GUIDE.md`](../LOCAL_TESTING_GUIDE.md), [`PRODUCTION_DEPLOYMENT_GUIDE.md`](../PRODUCTION_DEPLOYMENT_GUIDE.md), [`HUB_BACKUP_GUIDE.md`](../HUB_BACKUP_GUIDE.md)


## Work Guidance

- Follow the change lifecycle: propose → design → spec → tasks → implement → verify (tasks list includes bench tests per node)
- Keep spec requirements in SHALL + WHEN/THEN scenario format; implementation must satisfy every scenario
- Update `.openspec.yaml` `created` date and the relevant `spec.md` only as part of a change
- When hardware/firmware work happens, mark `tasks.md` checkboxes and cross-reference the actual sketches under `firmware/` (folder name must match `.ino` name)
- Out-of-scope boundaries are recorded in proposal/design (`hostapd`/`dnsmasq` stack, OverlayFS, `fsm_w_serial.ino` itself) — respect them unless a new change overrides

## Verification

- Requirements are verifiable via the scenarios in each `spec.md`; tasks.md §5 lists concrete bench tests
- Backend regression verification: `python -m pytest test_*.py` in `SERVERv5/v5/`
- No build tooling in `openspec/` itself — verification is against the target component suites and hardware bench tests
