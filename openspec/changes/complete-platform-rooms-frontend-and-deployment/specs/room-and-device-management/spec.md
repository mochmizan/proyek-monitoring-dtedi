## Purpose

Lets an admin organize devices into rooms, associate gateways with rooms, and turn a self-discovered pending device into an actively monitored, named, room-assigned device.

## ADDED Requirements

### Requirement: Rooms are admin-managed
The system SHALL let an `admin` create, rename, and delete rooms. A room SHALL NOT be deletable while devices are still assigned to it.

#### Scenario: Room created
- **WHEN** an admin creates a room with a unique name
- **THEN** the room is persisted and available for device assignment

#### Scenario: Deleting a room with assigned devices
- **WHEN** an admin attempts to delete a room that still has devices assigned to it
- **THEN** the deletion is rejected until those devices are reassigned or unpaired

### Requirement: Gateways are associated with a room
The system SHALL let an admin associate a registered hub (gateway) with a room, reusing the existing `hub_table` registry.

#### Scenario: Gateway assigned to a room
- **WHEN** an admin associates a hub with a room
- **THEN** devices reporting through that hub are attributable to that room by default

### Requirement: Pending devices can be paired into named, room-assigned devices
The system SHALL let an admin take a self-discovered pending device (already recorded via the existing unapproved-device flow) and assign it a display name, a room, and initial threshold configuration in one action, activating it.

#### Scenario: Admin pairs a pending device
- **WHEN** an admin submits a name, room, and initial thresholds for a pending device
- **THEN** the device becomes active (`is_active = true`), is associated with the chosen room, and its threshold configuration is stored

#### Scenario: Operator attempts to pair a device
- **WHEN** a user authenticated with the `operator` role attempts to pair or approve a device
- **THEN** the request is rejected as forbidden — pairing is admin-only, consistent with the existing device-approval endpoint's role requirement

### Requirement: Devices can be unpaired
The system SHALL let an admin unpair a device (clear its room assignment and mark it inactive) without deleting its historical telemetry.

#### Scenario: Device unpaired
- **WHEN** an admin unpairs an active device
- **THEN** the device's room assignment is cleared and it stops appearing in active room views, but its prior telemetry rows remain queryable by `dev_id`
