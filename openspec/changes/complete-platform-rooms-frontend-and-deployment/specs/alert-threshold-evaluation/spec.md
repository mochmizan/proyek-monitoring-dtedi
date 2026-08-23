## Purpose

Lets an admin configure per-device warning/critical thresholds and makes the system detect and log threshold breaches automatically as telemetry arrives, so operators have an alert history instead of only raw readings.

## ADDED Requirements

### Requirement: Per-device threshold configuration
The system SHALL let an admin configure, per device, a warning threshold, a critical threshold, a hysteresis margin, and a debounce duration for the metric(s) that device reports.

#### Scenario: Thresholds configured
- **WHEN** an admin sets warning/critical/hysteresis/debounce values for a device
- **THEN** those values are stored and used for subsequent threshold evaluation on that device's incoming telemetry

### Requirement: Threshold breaches are evaluated on ingest and logged
The system SHALL evaluate each incoming telemetry reading against the reporting device's configured thresholds as part of the same request that ingests the reading, and SHALL write a row to the alert log when a breach is detected.

#### Scenario: Reading exceeds critical threshold
- **WHEN** an incoming reading exceeds a device's configured critical threshold
- **THEN** a critical-severity alert is logged with the device, the value, the threshold breached, and a timestamp

#### Scenario: Reading returns to normal
- **WHEN** a reading returns below the warning threshold after a prior breach, accounting for the configured hysteresis margin
- **THEN** the alert is marked resolved (a resolved timestamp is recorded) rather than remaining open indefinitely

### Requirement: Debounce prevents alert flapping
The system SHALL NOT log a new alert for the same device/condition within its configured debounce duration of the previous alert for that same condition, to avoid flooding the alert log from a reading that oscillates near the threshold.

#### Scenario: Rapid oscillation near threshold
- **WHEN** a device's readings cross a threshold multiple times within its debounce duration
- **THEN** only one alert is logged for that condition until the debounce window elapses

### Requirement: Alerts are queryable with filters
The system SHALL expose an endpoint returning alert history filterable by room, device, severity, and time range, matching the filter dimensions the dashboard's Alerts page already expects.

#### Scenario: Filtered alert query
- **WHEN** a client requests alerts filtered by room and severity within a time range
- **THEN** only matching alert records are returned
