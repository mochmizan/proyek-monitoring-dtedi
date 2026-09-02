# HubGate V5 Concurrency Stress Benchmark Report

- **Database Engine**: `SQLite 3 (WAL mode) — Dev / Edge Target (Single-Writer Architecture)`
- **Execution Target**: `in-process`
- **Measured Duration**: `15.14 seconds`
- **Overall Result**: **PASSED (All Invariants Satisfied)**

## 1. Latency & Throughput Summary

| Workload / Endpoint | Total Req | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Errors | Status |
|---|---|---|---|---|---|---|---|
| GET /api/devices/{id}/history?range=30d | 9 | 0.6 | 677.03ms | 891.28ms | 891.28ms | 0 | PASS |
| POST /api/iot (Single Ingest) | 58 | 3.8 | 68.82ms | 173.89ms | 187.5ms | 0 | PASS |
| POST /api/iot/batch (75 pts/batch) | 117 | 7.7 | 191.02ms | 302.99ms | 388.17ms | 0 | PASS |
| GET /api/rooms (Outer Join Agg) | 53 | 3.5 | 137.19ms | 265.84ms | 365.7ms | 0 | PASS |
| GET /api/devices (Read-Only) | 53 | 3.5 | 144.03ms | 323.12ms | 358.79ms | 0 | PASS |
| GET /api/alerts (Composite Indexed) | 54 | 3.6 | 168.05ms | 527.56ms | 835.26ms | 0 | PASS |
| GET /api/rooms/{id}/map (Window Query) | 53 | 3.5 | 167.05ms | 353.08ms | 467.93ms | 0 | PASS |

## 2. Hardening Invariant Verification Matrix

| Invariant ID | Assertion Description | Measured Value | Target SLA | Result |
|---|---|---|---|---|
| `inv1_downsample_p95` | 30d History Downsampling P95 Latency | `891.28ms` | `< 1000.0ms` | **PASS** |
| `inv2_single_write_p95` | POST /api/iot Single-Write P95 Latency | `173.89ms` | `< 200.0ms` | **PASS** |
| `inv2_single_write_p99` | POST /api/iot Single-Write P99 Latency | `187.5ms` | `< 500.0ms` | **PASS** |
| `inv3_batch_write_p95` | POST /api/iot/batch Batch-Write P95 Latency | `302.99ms` | `< 350.0ms` | **PASS** |
| `inv3_batch_write_p99` | POST /api/iot/batch Batch-Write P99 Latency | `388.17ms` | `< 750.0ms` | **PASS** |
| `inv4_ingestion_throughput` | Ingestion Pipeline Throughput | `583.5 pts/sec` | `> 500.0 pts/sec` | **PASS** |
| `inv5_zero_database_locked_errors` | Database Locked (database is locked) Count | `0` | `== 0` | **PASS** |
| `inv5_zero_timeout_errors` | Timeout / Connection Drops Count | `0` | `== 0` | **PASS** |
| `inv5_zero_http_500_errors` | HTTP 500 Internal Server Errors Count | `0` | `== 0` | **PASS** |
