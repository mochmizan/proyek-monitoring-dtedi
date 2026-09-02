---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-telemetry-pipeline.md, wiki/concept-alert-engine.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/app/services/presence.py, server/app/routers/devices.py, server/app/services/scheduler.py, server/test_phase5_presence_nplus1.py, commit:8f8f6cd]
updated: 2026-09-02
---

# Presence Engine

The Presence Engine manages device connectivity state detection, offline alert generation, and automatic online recovery across the smsb IoT network. It is architected around a decoupled background sweeper, strict detection lag SLAs, and an idempotent read-only invariant across all consumer API endpoints.

## 1. Problem Context: Read-Time Mutation Bottleneck

In early revisions of HubGate V5, device presence checks were executed synchronously inside user read endpoints:
- `GET /api/devices` iterated through active devices, checked if `last_seen < now - 25s`, updated `last_status = "offline"`, and called `db.commit()` to persist state changes and insert `DEVICE_OFFLINE` alerts into `event_log`.
- `GET /api/rooms` and `GET /api/rooms/{id}/map` similarly triggered database mutations during normal browsing.

Under concurrent workloads (multiple browser tabs polling every 3 seconds while edge hubs streamed telemetry), read-induced write commits generated severe SQLite lock contention (`sqlite3.OperationalError: database is locked`), resulting in HTTP 500 crashes and delayed query responses.

## 2. Decoupled 5-Second Background Sweeper

The hardened Presence Engine completely divorces state evaluation from read requests, moving all mutation logic into a periodic background task:

1. **Scheduler Integration**: APScheduler executes `evaluate_device_presence_batch()` (`server/app/services/presence.py`) on a fixed 5-second interval (`PRESENCE_INTERVAL_SECONDS = 5`).
2. **Session Isolation**: The sweeper executes in an independent, scoped database session (`SessionLocal()`) with explicit rollback handling, ensuring presence evaluation errors never contaminate HTTP request sessions.
3. **N+1 Query Elimination**:
   - Fetches all active devices in a single query using eager loading: `select(dev_table).options(selectinload(dev_table.room)).where(dev_table.is_active == True)`.
   - Fetches all currently unresolved `DEVICE_OFFLINE` records from `event_log` in a single query, grouping them by `dev_id` in Python memory (`defaultdict(list)`).
4. **In-Memory State Transitions**:
   - Determines cutoff timestamp: $T_{\text{cutoff}} = \text{now}_{\text{UTC}} - 25\text{s}$ (`DEVICE_OFFLINE_WINDOW_SECONDS = 25`).
   - **Online to Offline Transition**: If a device's `last_seen < T_{\text{cutoff}}` and its current `last_status == "online"`, the sweeper transitions `dev.last_status = "offline"` and stages a `DEVICE_OFFLINE` warning alert in `event_log`.
   - **Offline to Online Transition**: If `last_seen >= T_{\text{cutoff}}` and `last_status != "online"`, the sweeper sets `dev.last_status = "online"` and stamps `resolved_at = now_utc` on all open offline alerts.
5. **Stale Pending Device Pruning**: Executes a single bulk `delete()` for unapproved devices (`is_active == False` and `room_id IS NULL`) older than 25 seconds.
6. **Conditional Commit**: The database session only executes `db.commit()` if state changes or prune deletions actually occurred (`has_state_changes`), minimizing disk write I/O.

## 3. Detection Lag SLA: 30 Seconds Maximum

The combination of the offline timeout window and the background sweeper schedule defines the system detection SLA:

$$\text{Detection Lag}_{\max} = \text{DEVICE\_OFFLINE\_WINDOW\_SECONDS} + \text{PRESENCE\_INTERVAL\_SECONDS} = 25\text{s} + 5\text{s} = 30\text{s}$$

- Best-case detection latency: 25.0 seconds (if hardware drops immediately before sweeper tick).
- Worst-case detection latency: 30.0 seconds (if hardware drops immediately after sweeper tick).
- All device disconnects are guaranteed to be flagged as `offline` and alerted within 30 seconds.

## 4. Idempotent Read-Only Invariant (`GET /api/devices`)

Read endpoints (`GET /api/devices`, `GET /api/rooms`, `GET /api/rooms/{id}/map`) are strictly read-only:
- They execute zero database write transactions (`db.commit() == 0`).
- Status is computed dynamically on-the-fly in Python during serialization:
  ```python
  d_seen = d.last_seen if (d.last_seen and d.last_seen.tzinfo is not None) else ...
  if not d.is_active:
      computed_status = "pending"
  elif d_seen and d_seen >= cutoff:
      computed_status = "online"
  else:
      computed_status = "offline"
  ```
- This guarantees zero lock contention between dashboard polling readers and telemetry ingestion writers.

## 5. Telemetry-Driven Fast Recovery

While offline transitions are detected by the 5-second background sweeper, online recovery is instantaneous:
- When valid telemetry arrives at `POST /api/iot` or `POST /api/iot/batch`, `resolve_offline_on_telemetry()` marks `device.last_status = "online"`, stamps `last_seen = now_utc`, and auto-resolves any open `DEVICE_OFFLINE` alerts in `event_log`.
- An informative `DEVICE_ONLINE` alert is recorded to acknowledge connectivity restoration.
- Recovery occurs within the same atomic commit as the telemetry insertion.
