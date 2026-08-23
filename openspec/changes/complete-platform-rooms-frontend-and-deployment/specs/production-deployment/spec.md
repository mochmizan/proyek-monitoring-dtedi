## Purpose

Defines the actual production deployment topology on the campus Ubuntu VPS: how the frontend and API are served together, and what must be true before this is considered "deployed."

## ADDED Requirements

### Requirement: Frontend and API are served same-origin via Nginx
The system SHALL serve the built frontend static assets and reverse-proxy the API under the same public origin/domain through Nginx, rather than as two separately-hosted origins.

#### Scenario: Public request to the dashboard
- **WHEN** a browser requests the dashboard's URL
- **THEN** Nginx serves the built frontend assets directly

#### Scenario: Public request to the API
- **WHEN** the frontend calls an `/api/...` path
- **THEN** Nginx reverse-proxies that request to the FastAPI application, on the same origin the frontend was served from

### Requirement: Production configuration uses real values, not development defaults
The system SHALL be deployed with `.env` populated with real production credentials (admin bootstrap, hub keys, database URL) and SHALL NOT be deployed with any placeholder/example value still in place.

#### Scenario: Pre-deployment check
- **WHEN** deployment is performed
- **THEN** every required environment variable has a real, non-placeholder value, verified before traffic is enabled

### Requirement: Database migrations are applied before traffic is enabled
The system SHALL have all pending additive migrations (rooms, thresholds, floor-plan markers, and any prior change's schema additions) applied to the production database before the updated application is put into service.

#### Scenario: Deployment sequencing
- **WHEN** a new version is deployed
- **THEN** `init_sqlv5.py`'s additive migrations are run against the production database before Uvicorn is restarted to serve the new code

### Requirement: The edge gateway is backed up before it is touched
The system's deployment process SHALL require a verified backup of the Raspberry Pi edge gateway (a full SD card image, or at minimum its NetworkManager/hostapd config, Mosquitto config, HubBrain systemd unit, `.env`, and `cert.crt`) to exist before any change that modifies the Pi's running configuration or application code is deployed to it.

#### Scenario: Deploying HubBrain changes to the physical Pi
- **WHEN** an updated HubBrain (offline cache, generalized command dispatch) is about to be deployed to the physical Raspberry Pi
- **THEN** a backup verification step confirms a recent backup exists before the deployment proceeds

#### Scenario: No backup exists yet
- **WHEN** no verified backup exists for the Pi that is about to be modified
- **THEN** the deployment is blocked until a backup is taken, rather than proceeding on trust
