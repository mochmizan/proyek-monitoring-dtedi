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

## Action Items for Future Implementation
- Update ESP8266 firmware (`WEMOS_TS`, `WEMOS_ATS`) to compute delta against previous published state before emitting MQTT JSON.
- Retain edge WAL FIFO pacing and server batch ingestion as backstop.
- Coordinate with hardware team testing via SSH tunnel (`ssh -N -L 1883:10.33.102.10:1883 genset@100.108.98.30`).
