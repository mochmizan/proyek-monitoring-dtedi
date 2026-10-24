---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-security-auth.md, wiki/entity-data-model.md, wiki/entity-dashboard-spa.md]
sources: [server/modelsv5.py, server/auth.py, server/app/routers/clusters.py, server/app/routers/memberships.py, dashboard/src/routes/clusters.tsx, server/test_cluster_system.py]
updated: 2026-10-21
---

# Cluster-Based Access Control (CBAC)

Cluster-Based Access Control organizes physical IoT deployments by location (clusters) and enforces strict multi-tenant boundary isolation between users assigned to different sites, while providing a global Super Admin (`root`) with system-wide governance.

## 1. Domain Concept: Cluster

A **Cluster** represents a discrete physical location, building, or campus facility (e.g., "Gedung DTEDI Barat", "Lab IoT"). Every cluster encapsulates:
- Connected IoT Devices (`dev_table.cluster_id`)
- Rooms and floor plans (`rooms.cluster_id`)
- Assigned user personnel and their cluster-specific roles (`user_cluster_memberships`)
- Granular permission matrix overrides (`cluster_role_permissions`)

## 2. Role Hierarchy & Multi-Tenancy

The authorization model separates global platform governance from localized operational access:

1. **Root / Super Admin (`role: root`)**:
   - Global platform authority.
   - Creates, edits, deactivates, and deletes clusters.
   - Assigns users to clusters and configures role permission matrices.
   - Has unrestricted read and write access across all clusters, devices, rooms, schedules, alerts, and audit logs.
2. **Cluster Admin (`role: admin`)**:
   - Scoped administrator for assigned cluster(s).
   - Manages devices (pairing, thresholds, metadata) and rooms within their cluster.
   - Creates schedules and controls field hardware within their cluster.
   - Cannot view or mutate devices, rooms, alerts, or schedules belonging to other clusters.
3. **Cluster Operator (`role: operator`)**:
   - Operational user for assigned cluster(s).
   - Issues commands to active devices (AC controls, ATS generator test run).
   - Manages scheduled automations within their cluster.
   - Cannot modify hardware alarm thresholds or pair/unpair devices.
4. **Cluster Viewer (`role: viewer`)**:
   - Read-only user for assigned cluster(s).
   - Inspects real-time telemetry, historical trend charts, and active alerts.
   - Strictly prohibited from executing control actions or modifying configuration.

## 3. Cluster Admin Scope & User Management

Cluster Admins possess delegated authority to administer personnel and review audit traces for their assigned cluster(s):
- **User Administration (`/api/admin/users`)**: Cluster Admins can create and manage (`status`, password reset, session revoke, deletion) operator and viewer accounts belonging to their cluster. They cannot create or mutate Root accounts or other Cluster Admins.
- **Audit & Activity Logs (`/api/admin/users/audit-logs`, `/api/admin/users/activity-logs`)**: Activity and security audit trails are filtered to actions performed by or targeting members of the admin's assigned clusters.
- **Role Persistence & Self-Healing**: User roles are directly preserved upon creation (e.g. `role: "admin"` remains `"admin"`, avoiding legacy `"member"` casting). During authentication (`/api/auth/login` and `/api/auth/me`), any legacy `"member"` accounts automatically self-heal to their assigned cluster membership role.

## 4. Room & Sensor Provisioning per Cluster

Cluster resources are governed with fine-grained assignment and modification controls:
- **Cluster Room Lifecycle (`/api/clusters/{id}/rooms`)**: Root can directly create, rename, and delete rooms inside a cluster, or assign/unassign existing rooms via `/api/clusters/{id}/assign-room` and `/api/clusters/{id}/unassign-room`.
- **Sensor Management (`/api/clusters/{id}/devices/{dev_id}`)**: Root can assign sensors to clusters and specific rooms within the cluster, rename sensor labels, and unassign devices back to the unallocated pool.
- **Unassigned Resources Pool (`/api/clusters/unassigned-resources`)**: Exposes available rooms and devices not currently assigned to any cluster.
- **Cluster Member Governance (`/api/clusters/{id}/members`)**: Root can inspect all active members and their assigned cluster roles, or provision new members via `/api/memberships`.

## 5. Data Scoping & Query Isolation Invariant

Access control is enforced at the database query level on every consumer endpoint:

- **Devices (`/api/devices`, `/api/devices/{id}`, `/api/devices/{id}/history`)**:
  - Filtered by `dev_table.cluster_id.in_(user_clusters)` for assigned non-root users.
  - Direct ID lookups against devices in other clusters reject with HTTP 403 Forbidden.
- **Rooms (`/api/rooms`, `/api/rooms/{id}/map`)**:
  - `GET /api/rooms` applies cluster scoping via SQL subquery while preserving the `single-query GET /api/rooms` architectural SLA.
  - Room map accesses across cluster boundaries return HTTP 403 Forbidden.
- **Alerts (`/api/alerts`)**:
  - Alerts in `event_log` are filtered by device or room cluster affiliation (`dev_table.cluster_id` / `rooms.cluster_id`).
  - Cross-cluster filter queries return empty result sets (`AlertListResponse(total=0, alerts=[])`).
- **Schedules (`/api/schedules`)**:
  - Non-root users can only view, create, modify, delete, or trigger schedules associated with devices in their assigned clusters.
- **Backward Compatibility Fallback**:
  - Unassigned legacy users (e.g. system accounts created before cluster 도입) retain fallback visibility to unassigned legacy entities (`cluster_id IS NULL`), ensuring existing verification pipelines continue to operate without regression.

## 6. Configurable Permission Matrix

Each cluster supports custom overrides over the 14 standard permission flags (`view_dashboard`, `view_devices`, `view_monitoring`, `view_history`, `view_alerts`, `view_reports`, `control_devices`, `pair_devices`, `edit_devices`, `delete_devices`, `manage_schedules`, `manage_rooms`, `manage_users`, `export_data`). Stored in `cluster_role_permissions`, explicit cluster overrides supersede the platform defaults (`DEFAULT_PERMISSIONS` in `auth.py`).
