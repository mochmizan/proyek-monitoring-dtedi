---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubbrain-v5.md, wiki/entity-hubgate-v5.md, wiki/entity-ats-firmware-chain.md, wiki/entity-dashboard-spa.md, wiki/concept-time-conventions.md, wiki/concept-downsampling-v2.md, wiki/concept-presence-engine.md, wiki/concept-alert-engine.md, wiki/workstream-backend-hardening-v5.md]
sources: [hub/main.py, server/app/routers/iot.py, server/app/dependencies.py, server/schemasv5.py, server/modelsv5.py, commit:8f8f6cd, commit:9961f5c, commit:0fd2e81, commit:d1225f9]
updated: 2026-09-02
---

# Telemetry Pipeline

The telemetry pipeline governs the end-to-end flow of sensor metrics from physical edge hardware to long-term database storage and real-time dashboard visualizations. It is engineered for atomic transactions, replay idempotency, burst suppression, and high concurrency under network partitions.

## 1. Edge Uplink & Forwarding Flow

1. **Sensor Measurement**: ESP8266 nodes sample sensor hardware (SHT30 temperature/humidity or Pro Mini ATS FSM) and publish JSON telemetry to the Pi-local Mosquitto broker on `hs109rs/{hub_name}/{dev_type}/{dev_id}`.
2. **Edge Filtering & Forwarding**: HubBrain (`hub/main.py`) validates device IDs against its active local whitelist. Non-whitelisted IDs trigger throttled registration alerts (`POST /api/iot/unapproved`), while approved device messages are dispatched over HTTPS to HubGate.
3. **Transport Modes**: Under normal network conditions, HubBrain forwards telemetry either singly to `POST /api/iot` or in batches of up to 1000 items (typically 75-100) via `POST /api/iot/batch` using `X-Hub-ID` and `X-Hub-Key` authentication headers.
4. **Offline WAL Buffering & Timestamp Preservation**: When campus LAN or upstream internet is interrupted, forwarding failures trigger the edge write-ahead log (bounded to 20,000 rows FIFO, 7-day TTL). Upon link restoration, the replay worker drains buffered rows paced at 0.35s/row and stamps each record with `_hub_created_at` (the UTC epoch of physical capture). The server parses this epoch for `event_time`, preserving true historical capture times across multi-hour outages instead of collapsing them to the replay timestamp.

## 2. In-Memory Throttled Heartbeats (`HubAuthCache`)

During high-volume ingestion, updating hub liveness (`last_seen`) on every incoming HTTP request generates write lock contention and redundant transactions. HubGate mitigates this using `HubAuthCache` (`server/app/dependencies.py`):
- Uses an in-memory double-checked cache with a lock-free read path to verify credentials.
- Throttles database heartbeat updates to once every 30.0 seconds per hub.
- Stages the timestamp update on the session `hub_table` instance without committing immediately (`stage_hub_heartbeat`).

## 3. Atomic Single-Transaction Ingestion (CRIT-01 Resolution)

Prior to hardening, hub authentication and telemetry insertion executed in separate database transactions. Under high concurrency, the early auth commit acquired SQLite write locks and created deadlock collisions with concurrent telemetry writes.

In the hardened architecture, the entire ingestion lifecycle executes within a single atomic database transaction:
$$\text{Single Atomic Commit} = \text{Staged Hub Heartbeat} + \text{Bulk Telemetry Insert} + \text{Presence Transition} + \text{Alert Evaluation}$$
If any validation fails or an unhandled exception occurs, `db.rollback()` cleanses the entire transaction, leaving no partial state or corrupted liveness records.

## 4. WAL Replay Idempotency (`on_conflict_do_nothing`)

During network flappings or edge replay retries, telemetry items may be transmitted more than once. The pipeline guarantees strict idempotency:
1. **Deterministic Primary Keys**: Every telemetry record generates a deterministic UUID:
   $$\text{data\_id} = \text{uuid5}(\text{NAMESPACE\_OID}, \text{dev\_id} + \text{":"} + \text{timestamp\_iso})$$
2. **Conflict Resolution**: Writes pass through `bulk_insert_or_ignore()` using dialect-native conflict resolution:
   - PostgreSQL 16: `INSERT ... ON CONFLICT (dev_id, timestamp) DO NOTHING`
   - SQLite 3: `INSERT ... ON CONFLICT (dev_id, timestamp) DO NOTHING` with automated fallback to `INSERT OR IGNORE`
3. **Unique Constraints**: Backed by `uq_temp_dev_timestamp`, `uq_ats_dev_timestamp`, and `uq_data_dev_timestamp` on `(dev_id, timestamp)`. Duplicate rows are discarded silently without rolling back the transaction.

## 5. In-Batch Deduplication & Alert Burst Suppression

When draining a WAL queue containing thousands of buffered historical readings, naive processing causes severe performance degradation and alert floods. HubGate applies two layers of batch optimization in `POST /api/iot/batch`:
1. **In-Batch Deduplication**: The endpoint tracks `(dev_id, timestamp)` tuples across the batch payload (`seen_temp`, `seen_ats`, `seen_data`). Duplicates within the same batch payload are filtered in Python memory before generating SQL insert batches.
2. **Alert Burst Suppression**: Evaluating threshold rules on every buffered row across an outage could generate thousands of redundant alerts. The batch handler tracks the latest reading per device in memory (`latest_reading_per_dev`). Alert threshold checks (`evaluate_device_thresholds`) and presence recovery (`resolve_offline_on_telemetry`) are executed strictly once per unique device using its newest reading.

## 6. Downlink & Dashboard Consumption

Data persisted in `temperature_data` and `ats_data` is served to the frontend SPA via `GET /api/devices/{id}/history`, which aggregates data into 1000 buckets using [concept-downsampling-v2.md](concept-downsampling-v2.md). The dashboard renders live updates using TanStack Query polling at `POLL_MS=3000` with stale-while-revalidate caching (`keepPreviousData`), displaying 3-panel stacked electrical charts and dynamic min/max envelope bands without blanking or layout shifting.

