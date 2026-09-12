---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-telemetry-pipeline.md, wiki/entity-dashboard-spa.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/app/routers/devices.py, server/test_device_history.py, server/test_phase2_downsampling.py, server/test_phase6_verification_benchmark.py, dashboard/src/hooks/useDeviceHistory.ts, commit:8f8f6cd]
updated: 2026-09-12
---

# Downsampling V2

Downsampling V2 provides single-pass, bounded-cardinality aggregation for device history queries (`GET /api/devices/{id}/history`). It guarantees consistent response times, exact envelope bounds, and constant memory overhead regardless of underlying dataset size across 30-day time ranges.

## 1. Grafana-Aligned Time-Bucket Architecture

Standard IoT time-series platforms (such as Grafana and Prometheus) downsample continuous metrics into discrete chronological buckets aligned with target display resolution. Rather than pulling large volumes of raw rows to the client or worker process, Downsampling V2 executes mathematical bucketing directly within the database engine in a single SQL pass.

Given a requested time range $[T_{\text{start}}, T_{\text{end}}]$ and target output cardinality `max_points` (default 1000):

$$\Delta T = T_{\text{end}} - T_{\text{start}} \quad (\text{in seconds})$$

$$\text{bucket\_seconds} = \max\left(1, \left\lfloor \frac{\Delta T}{\text{max\_points}} \right\rfloor\right)$$

Every recorded timestamp is projected into an integer bucket identifier representing the beginning of that time window:

$$\text{bucket\_ts} = \left\lfloor \frac{\text{epoch}(\text{timestamp})}{\text{bucket\_seconds}} \right\rfloor \times \text{bucket\_seconds}$$

## 2. Dialect-Aware Integer Epoch Math

To avoid string parsing overhead (`strftime('%s')` in SQLite or text conversions in PostgreSQL), Downsampling V2 uses native C-level epoch extraction:

- **SQLite 3.38+**: Utilizes the native C-level function `func.unixepoch(timestamp)`:
  ```sql
  CAST(FLOOR(unixepoch(timestamp) / :bucket_seconds) * :bucket_seconds AS INTEGER) AS bucket_ts
  ```
  This eliminates Python and SQLite string-formatting overhead, providing a ~2x performance increase over legacy `cast(strftime('%s', timestamp), Integer)`.
- **PostgreSQL 16**: Utilizes dialect-native `EXTRACT(epoch FROM timestamp)`:
  ```sql
  CAST(FLOOR(EXTRACT(epoch FROM timestamp) / :bucket_seconds) * :bucket_seconds AS INTEGER) AS bucket_ts
  ```

Buckets are grouped and sorted using `GROUP BY bucket_ts ORDER BY bucket_ts ASC`.

## 3. Min/Max Envelope Models

A fundamental weakness of naive downsampling (e.g. standard averages or LTTB decimation) in electrical and mechanical monitoring is the attenuation of transients. Averaging 100 readings across a 5-minute bucket smooths over brief PLN brownouts, genset voltage spikes, and starter battery cranking sags.

Downsampling V2 solves this by aggregating average values alongside exact minimum and maximum envelopes in the same query:

- **Temperature & Humidity Telemetry (`temperature_data`)**:
  - Averages: `AVG(temp) AS temp`, `AVG(humid) AS humid`
  - Envelopes: `MIN(temp) AS temp_min`, `MAX(temp) AS temp_max`, `MIN(humid) AS humid_min`, `MAX(humid) AS humid_max`
- **ATS Electrical Telemetry (`ats_data`)**:
  - PLN Grid AC: `AVG(pln) AS pln`, `MIN(pln) AS pln_min`, `MAX(pln) AS pln_max`
  - Genset AC: `AVG(genset) AS genset`, `MIN(genset) AS genset_min`, `MAX(genset) AS genset_max`
  - Starter Battery DC: `AVG(aki) AS aki`, `MIN(aki) AS aki_min`, `MAX(aki) AS aki_max`
  - Discrete Flags: `MAX(state) AS state`, `MAX(auto_mode) AS auto_mode`, `MAX(emergency) AS emergency`

The dashboard renderer draws semi-transparent envelope bands behind primary metric lines, allowing operators to visually inspect transient electrical anomalies.

## 4. Cardinality Bounds & Sub-1000 Bypass

1. **Sub-1000 Bypass**: Before executing aggregation, the query counts candidate rows in the requested window using the composite index. If total matching rows $\le 1000$, the database skips `GROUP BY` execution entirely and returns unaggregated raw telemetry in ascending order. This guarantees zero statistical distortion for short time ranges (e.g. 1h, 6h).
2. **Strict Cardinality Upper Bound**: For ranges requiring aggregation, the number of returned bucket rows is mathematically bounded to $\le \text{max\_points} + 5$ (bounded by bucket alignment). Payloads remain predictable, protecting frontend browser tabs from memory exhaustion.

## 5. SARGable Composite Index Utilization & SLAs

All history queries construct SARGable predicates filtering on `dev_id = :dev_id AND timestamp >= :start_time AND timestamp <= :end_time`. These filter expressions match the leading keys of composite indexes:
- `idx_temp_dev_timestamp(dev_id, timestamp DESC)` on `temperature_data`
- `idx_ats_dev_timestamp(dev_id, timestamp DESC)` on `ats_data`

The database engine navigates directly to the target device's time range via a B-tree range scan, avoiding full-table sequential scans.

**Performance SLAs & Measured Baseline**:
- PostgreSQL 16 (Active Production Database): 30-day history downsampling over 1,000,000 rows P95 < 300ms.
- SQLite 3 WAL (Edge / Dev Target): 30-day history downsampling over 1,000,000 rows P95 < 1000ms (Measured baseline: 891.28ms P95).