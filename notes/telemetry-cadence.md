# Telemetry Cadence & Transmission Standards (Roadmap)

Context: Hardware team discussion regarding telemetry interval tuning to balance transient capture resolution with server ingestion load and database storage bloat.

## Standards Reference

1. ASHRAE Guideline 36 (High-Performance Sequences of Operation for HVAC Systems):
   - Environmental monitoring (ambient temperature and relative humidity): 1-minute (60s) nominal sampling.
   - Closed-loop dynamic HVAC control (AC setpoint feedback): 10-second sampling.
   - Static threshold: fluctuations under 0.2°C should not trigger immediate event publishing.

2. NFPA 110 Level 1 (Emergency and Standby Power Systems):
   - Active generator run / ATS transfer transients: 1-second sampling cadence for voltage, frequency, and battery voltage. High-resolution telemetry required to detect voltage sags, cranking dips (starter battery < 11.2V), and transfer switch timing.
   - Standby / quiescent monitoring: 10s to 30s sampling cadence is sufficient when utility mains (PLN) is normal and generator is stopped.

3. Sparkplug B / Report-by-Exception (RBE):
   - Deadband-based transmission: edge node publishes telemetry only when an analog metric deviates by more than a configured deadband threshold from the last published value:
     - Temperature deadband: ΔT >= 0.2°C
     - Humidity deadband: ΔRH >= 1.0%
     - AC Voltage deadband: ΔV >= 1.0V (mains / genset)
     - DC Voltage deadband: ΔV >= 0.1V (starter battery)
   - Max reporting interval (heartbeat): if no threshold breach occurs within 60s (environmental) or 30s (ATS), emit a heartbeat reading to confirm node presence.

## Implementation Status
- **Phase 1: Edge Hub Adaptive Telemetry Filter & SQLite WAL PRAGMA Tuning (COMPLETED)**:
  - Implemented `hub/filter.py` with pure functional core `evaluate_telemetry_filter()` (< 0.05ms execution budget, measured at ~12µs) and thread-safe shell `AdaptiveTelemetryFilter`.
  - Tuned SQLite WAL PRAGMAs in `hub/main.py`: `PRAGMA wal_autocheckpoint = 1000;`, `PRAGMA cache_size = -8000;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA busy_timeout = 10000;`.
  - Verified write suppression invariant: 50 steady-state frames during network outage write exactly 1 SQLite row (98.0% suppression).
  - Instant state transition bypass verified (<100ms) activating 2.0s burst rate for 60 seconds.
  - Comprehensive test suite in `hub/test_telemetry_filter.py` (15/15 passing) and regression verified in `hub/test_edge_resilience.py` (13/13 passing).

- **Phase 2: Central Backend Presence Engine Alignment (COMPLETED)**:
  - Type-aware offline evaluation in `server/app/services/presence.py` (`DEVICE_OFFLINE_THRESHOLDS`: ATS: 180s, AC/ACC: 360s, TS: 900s).
  - Multi-tier gap floors in dashboard and presence flapping tests (27/27 passing).

- **Phase 3: Firmware Fleet Publish Cadence & Deadbands (COMPLETED)**:
  - `WEMOS_TS`: 300,000 ms (5m) steady heartbeat, 5,000 ms rate-limit, 2,000 ms sensor sampling, 1 Hz OLED display refresh, $\Delta T \ge 0.2^\circ\text{C}$, $\Delta\text{RH} \ge 2.0\%$, force publish on sensor error / recovery.
  - `WEMOS_ATS`: 60,000 ms (60s) steady heartbeat, decoupled 500 ms Pro Mini UART polling, dynamic burst mode (2.0s cadence for 60s) with instant 0ms forward on discrete state changes (`nowState`, `autoMode`, `emergency`, `pln_relay`, `gen_relay`, `alarm`), electrical deadbands ($\Delta V_\text{PLN} \ge 1.0\text{V}$, $\Delta V_\text{GEN} \ge 1.0\text{V}$, $\Delta V_\text{AKI} \ge 0.1\text{V}$), 2,000 ms rate-limit, static bounded buffer safety (`char[512]`, `char[65]`).
  - `WEMOS_AC`: 120,000 ms (2m) steady heartbeat, instant publish on AC downlink/serial command execution (0ms ACK), $\Delta T \ge 0.5^\circ\text{C}$, $\Delta\text{RH} \ge 2.0\%$, 5,000 ms rate-limit, 2,000 ms sensor sampling, 1 Hz OLED.
  - `PROMINI`: Canonical uncorrupted state preserved and verified against git.
  - Automated verification tool added: `python tools/verify_firmware.py`.

- **Phase 4: Frontend Dashboard Harmonization & Chart Gap Alignment (COMPLETED)**:
  - Added `GAP_FLOOR_BY_TYPE_MIN` (`{ TS: 15, AC: 6, ACC: 6, ATS: 3, DEFAULT: 3 }` in minutes) and `CADENCE_BY_TYPE` nominal cadence metadata in `dashboard/src/lib/constants.ts`.
  - Implemented pure functional `getGapThresholdMinutes(devType, rangeMinutes)` and updated `getGapThresholdMs` in `dashboard/src/lib/chartUtils.ts` to prevent false outage hatches during normal RBE cadences and dynamically scale for extended historical windows (24h: 24m, 7d: 168m, 30d: 720m).
  - Added reporting cadence badges ("Cadence: 5m RBE", "1m RBE", "2m RBE") in device detail header (`dashboard/src/routes/device.$deviceId.tsx`).
  - Unit tests in `dashboard/src/lib/chartUtils.test.ts` (21/21 passing) and vitest suite (209/209 passing across 23 suites).


