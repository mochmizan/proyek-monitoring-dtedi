## Purpose

Replaces the dashboard's simulated Zustand mock data and non-functional login with real calls against HubGate, so the UI reflects actual device state, actual telemetry, and actual authenticated sessions.

## ADDED Requirements

### Requirement: Server data is owned by TanStack Query, not client-side simulation
The system SHALL fetch rooms, devices, telemetry, and alerts via TanStack Query against real HubGate endpoints. The system SHALL NOT retain the Zustand-based random-walk telemetry simulator once real endpoints are wired.

#### Scenario: Dashboard loads room data
- **WHEN** the dashboard's home view loads
- **THEN** room cards and the node table are populated from real API responses, not simulated values

### Requirement: Live views poll for updates
The system SHALL refresh room and device views on a short polling interval (2–5 seconds) while a relevant view is open, rather than relying on a client-side timer that fabricates new values.

#### Scenario: Room detail view open
- **WHEN** a user has a room detail view open
- **THEN** displayed readings update within the polling interval to reflect the latest ingested telemetry, without a full page reload

### Requirement: Login and route guards use real sessions
The system SHALL submit the login form to `POST /api/auth/login`, and its route guards SHALL check session validity via `GET /api/auth/me` rather than any client-side mock authentication state.

#### Scenario: Successful login
- **WHEN** a user submits correct credentials on the login page
- **THEN** they are redirected to their originally requested route (per the existing `redirect` query param design) and subsequent route guards recognize them as authenticated

#### Scenario: Unauthenticated access to a guarded route
- **WHEN** an unauthenticated user navigates directly to a guarded route
- **THEN** they are redirected to login with a `redirect` param pointing back to the originally requested route

### Requirement: Frontend and API share an origin
The system SHALL serve the built frontend static assets from the same origin as the API in production (via Nginx), and SHALL use the Vite dev-server proxy (not CORS) to keep requests same-origin during local development.

#### Scenario: Production request
- **WHEN** the deployed frontend makes an authenticated API request
- **THEN** the request is same-origin, so the `SameSite=Lax` session cookie is attached automatically without any cross-origin cookie configuration
