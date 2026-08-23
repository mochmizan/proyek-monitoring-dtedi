## Purpose

Lets an admin upload a room's floor plan image and position device markers on it by percentage coordinates, so the dashboard's map view can render device locations.

## ADDED Requirements

### Requirement: Floor plan image is stored per room
The system SHALL let an admin upload one floor plan image per room, stored on local disk under a path served statically by Nginx (not a new object-storage service), and SHALL replace the previous image if a new one is uploaded for the same room.

#### Scenario: Floor plan uploaded
- **WHEN** an admin uploads an image for a room that has none yet
- **THEN** the image is stored and its URL becomes retrievable for that room

#### Scenario: Floor plan replaced
- **WHEN** an admin uploads a new image for a room that already has one
- **THEN** the previous image is replaced and the old file is removed

### Requirement: Device markers use percentage coordinates
The system SHALL store each paired device's marker position as `x`/`y` percentages (0–100) relative to its room's floor plan image, so marker position remains correct regardless of the image's rendered size on screen.

#### Scenario: Marker positioned during pairing
- **WHEN** an admin positions a device's marker on the floor plan during pairing
- **THEN** the `x`/`y` percentage coordinates are stored alongside that device's room assignment

### Requirement: Rooms without a floor plan degrade gracefully
The system SHALL indicate clearly when a room has no floor plan uploaded yet, rather than erroring, so the map view can show a fallback state.

#### Scenario: Map requested for a room with no floor plan
- **WHEN** the map view is requested for a room that has no uploaded floor plan image
- **THEN** the response indicates no image is available rather than returning an error
