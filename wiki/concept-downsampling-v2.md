---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-backend-hardening-v5.md]
sources: [server/app/routers/devices.py, server/test_phase2_downsampling.py, server/test_phase6_verification_benchmark.py]
updated: 2026-09-02
---

# Downsampling V2

Downsampling V2 provides single-pass, bounded-cardinality aggregation for device history queries (GET /api/devices/{id}/history). It guarantees consistent response times, exact envelope bounds, and constant memory overhead regardless of underlying dataset size across 30-day time ranges.

## 1. Single-Pass Epoch Bucketing

Rather than executing multiple scans or client-side filtering, aggregation occurs in the database engine using single-pass grouping on mathematical time buckets:

\\text{bucket\\_seconds} = \\max\\left(1, \\lfloor \\frac{\\text{duration\\_sec}}{\\text{max\\_points}} \\rfloor\\right)

The SQL bucket expression is dialect-aware:
- **SQLite 3.38+**: Uses native C-level unc.unixepoch(timestamp):
  \\text{bucket\\_ts} = \\lfloor \\frac{\\text{unixepoch}(\\text{timestamp})}{\\text{bucket\\_seconds}} \\rfloor \\times \\text{bucket\\_seconds}
  This provides ~2x performance over legacy string formatting (cast(strftime('%s', timestamp), Integer)).
- **PostgreSQL 16**: Uses CAST(FLOOR(EXTRACT(epoch FROM timestamp) / bucket_seconds) * bucket_seconds AS INTEGER).

## 2. Min/Max Envelopes

Every bucket computes both average values and exact min/max envelopes in a single aggregation step:
- **Temperature & Humidity**: AVG(temp), MIN(temp) AS temp_min, MAX(temp) AS temp_max, AVG(humid), MIN(humid) AS humid_min, MAX(humid) AS humid_max.
- **ATS Readings**: AVG(pln), MIN(pln) AS pln_min, MAX(pln) AS pln_max, AVG(genset), MIN(genset) AS genset_min, MAX(genset) AS genset_max, AVG(aki), MIN(aki) AS aki_min, MAX(aki) AS aki_max.

This preserves sharp spikes, sags, and transient fault conditions that standard averaging filters out.

## 3. Cardinality Bounds & Sub-1000 Bypass

- **Sub-1000 Bypass**: If the total matching rows in the requested window is <= 1000 points, the query bypasses grouping and returns exact, unaggregated points in ascending order.
- **Bounded Output**: Grouped queries return at most max_points + 5 records (bounded by integer division alignment), ensuring client renderers never receive unbounded payloads.

## 4. Performance SLA & SARGable Indexes

The history read path leverages composite indexes:
- idx_temp_dev_timestamp: 	emperature_data(dev_id, timestamp.desc())
- idx_ats_dev_timestamp: ts_data(dev_id, timestamp.desc())

**Performance SLA**:
- PostgreSQL Production Target: 30-day history downsample P95 < 300ms.
- SQLite Dev/Edge Target: 30-day history downsample P95 < 1000ms.