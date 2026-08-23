## Purpose

Prevents silent telemetry loss when the Raspberry Pi's connection to HubGate is unavailable, and fixes the command dispatcher so it correctly routes downlink commands for any device type rather than one hardcoded topic.

## ADDED Requirements

### Requirement: Failed telemetry forwarding is cached locally, not dropped
The system SHALL write a telemetry payload to a local SQLite WAL-mode cache when the HTTPS forward to HubGate fails, instead of discarding it.

#### Scenario: Cloud link is down
- **WHEN** HubBrain's forward of a telemetry payload to HubGate fails (network error or non-2xx response)
- **THEN** the payload is written to the local SQLite cache rather than lost

### Requirement: Cached telemetry replays in order when connectivity recovers
The system SHALL replay cached telemetry to HubGate in the original chronological order (oldest first) once connectivity is restored, at a paced rate that does not flood the cloud ingestion endpoint, and SHALL remove each record from the local cache only after it is successfully forwarded.

#### Scenario: Connectivity restored with a backlog
- **WHEN** HubBrain successfully reconnects to HubGate after an outage with cached records pending
- **THEN** cached records are forwarded oldest-first at a paced rate, each removed from the local cache upon confirmed delivery

#### Scenario: Live telemetry arrives during backlog replay
- **WHEN** new telemetry arrives while a backlog replay is in progress
- **THEN** the new telemetry is forwarded immediately rather than queued behind the backlog

### Requirement: Command dispatch topic is resolved per device, not hardcoded
The system SHALL derive the MQTT downlink topic for a pending command from the target device's type/identity, rather than using a single hardcoded topic string, so command dispatch works correctly for ATS, AC, and any future device type without per-type code duplication.

#### Scenario: ATS command dispatched
- **WHEN** HubBrain retrieves a pending command for an ATS device
- **THEN** it publishes to that device's ATS command topic, derived from its type/identity, not a hardcoded string shared across device types

#### Scenario: AC command dispatched
- **WHEN** HubBrain retrieves a pending command for an AC device
- **THEN** it publishes to that device's AC command topic, resolved the same way, without requiring a separate hardcoded topic constant per device type
