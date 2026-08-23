## Purpose

Lets the full pipeline — device telemetry through to the dashboard — be exercised and verified on a laptop, with no physical hardware and no access to the VPS or the Raspberry Pi, before any change is deployed to either.

## ADDED Requirements

### Requirement: A Docker Compose stack provides Postgres and Mosquitto locally
The system SHALL provide a Docker Compose configuration that starts a local Postgres instance and a local Mosquitto broker (with authentication enabled, matching production's `allow_anonymous false` posture) with a single command.

#### Scenario: Stack started
- **WHEN** a developer runs the local stack's start command
- **THEN** a Postgres instance and an authenticated Mosquitto broker are both reachable on localhost, ready for HubGate and HubBrain to connect to

### Requirement: Mock publishers simulate device telemetry
The system SHALL provide scripts able to publish valid TS, ATS, and AC telemetry payloads to the local Mosquitto broker, matching the real schemas (`TSData`, `ATSData`, `ACData`), so ingestion and routing can be verified without flashing or wiring any physical node.

#### Scenario: Mock ATS telemetry published
- **WHEN** a developer runs the mock ATS publisher
- **THEN** a valid `ATSData`-shaped payload is published to the local broker's ATS data topic, and a locally running HubBrain forwards it to a locally running HubGate, which routes it into `ats_data`

### Requirement: HubGate and HubBrain run locally via configuration only
The system SHALL let both HubGate and HubBrain run against the local stack purely through environment variable configuration (database URL, MQTT host, hub keys), with no code changes required to switch between local and production targets.

#### Scenario: Running HubBrain locally
- **WHEN** HubBrain is started with its `.env` pointed at the local Mosquitto broker and local HubGate instance
- **THEN** it operates identically to its production configuration, forwarding telemetry and polling for commands against the local stack instead

### Requirement: The local setup is documented and reproducible
The system SHALL include a README describing how to start the stack, run the mock publishers, and run HubGate/HubBrain against it, so any team member can reproduce the test environment without prior context.

#### Scenario: New team member sets up locally
- **WHEN** a team member follows the local testing README from a clean checkout
- **THEN** they can bring up the full pipeline and observe mock telemetry reaching the database without needing to ask how
