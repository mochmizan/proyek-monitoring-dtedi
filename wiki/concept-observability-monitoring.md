---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-devops-infrastructure.md, wiki/entity-hubgate-v5.md, wiki/concept-telemetry-pipeline.md, wiki/concept-alert-engine.md, wiki/concept-production-readiness.md, wiki/workstream-production-grade-roadmap.md]
sources: [server/app/core/logging.py, server/app/main.py, server/app/services/presence.py, deploy/journald.conf.dropin, tools/benchmark_concurrency_stress.py]
updated: 2026-09-03
---

# Observability & Monitoring Architecture

Observability across the SMSB platform encompasses log aggregation, metrics collection, distributed health probing, and event notification dispatching across Central Server (`hubgatev5`), Edge Gateway (`hubbrain`), and physical microcontroller nodes.

---

## 1. Logging Architecture & Runtime Deficits

The logging subsystem provides transaction visibility, authentication audits, and failure tracing.

### Current Implementation (`server/app/core/logging.py`)
HubGate V5 defines a structured logging configuration using standard library `logging.config.dictConfig`:
```python
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "standard": {
            "format": "%(asctime)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["default"],
    },
}
```

### The Structured Logging Dependency Gap
Inspection of runtime dependencies reveals a critical discrepancy:
- `server/app/core/logging.py` attempts to import `pythonjsonlogger` when `LOG_FORMAT=json`.
- However, `python-json-logger` is **omitted from `server/requirements.txt`**.
- As a consequence, on production deployments, `use_json` evaluates to `False`, silently falling back to unstructured plain text:
  ```
  2026-09-03 14:15:22,104 INFO uvicorn.access: 127.0.0.1:48292 - "POST /api/iot/batch HTTP/1.0" 200
  ```
- **Consequence**: Log aggregators (Grafana Loki, Elasticsearch) cannot index fields natively without fragile runtime regex parsing.

### Missing Contextual Correlation Metadata
Application log messages lack request-scoped correlation metadata:
- **No Correlation IDs**: No `request_id` or `trace_id` propagated through HTTP middleware. Log lines emitted across multiple threads or async tasks cannot be reconstructed into a single transaction trace.
- **No Identity Enrichment**: Ingestion logs do not automatically record `hub_id`, client IP (`X-Forwarded-For`), batch cardinality, or execution time in structured fields.
- **Retention Bottleneck**: Host logging is bounded by `deploy/journald.conf.dropin` (`SystemMaxUse=100M`). Under high ingestion frequency or burst replay conditions, journald rotates historical logs within hours, destroying diagnostic audit trails.

### Edge Gateway Logging Architecture (`hub/main.py`)
At the edge gateway tier:
- HubBrain initializes logging via basic standard library configuration:
  ```python
  logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s [%(levelname)s] %(message)s",
      handlers=[logging.StreamHandler(sys.stdout)]
  )
  ```
- All log events (MQTT message receipts, unapproved device warnings, HTTPS uplink attempts, WAL queue pushes and drains) are emitted as flat text to stdout and captured by `journald`.
- Neither structured JSON nor syslog severity tagging is implemented.
- Operational metrics (e.g. offline SQLite cache row count, replay batch sizes, network drop frequencies) are only visible as free-text log strings, preventing programmatic alerting at the edge.

---

## 2. Metrics Collection & Exposition (The Observability Void)

The platform currently operates without any automated metrics exposition or time-series infrastructure monitoring.

### Absence of Metrics Endpoint
- **No Prometheus Exporter**: Neither FastAPI (`hubgatev5`) nor edge HubBrain exposes a `/metrics` or `/metrics/prometheus` HTTP endpoint.
- **No APM Client**: No metrics collection libraries (such as `prometheus-client`, `prometheus-fastapi-instrumentator`, or `statsd`) are included in `server/requirements.txt` or `hub/main.py`.

### Critical Unmonitored Operational Signals

```
+-------------------------------------------------------------------------+
| OPERATIONAL SIGNALS CURRENTLY INVISIBLE IN PRODUCTION                   |
+-------------------------------------------------------------------------+
| Ingestion & Pipeline:                                                   |
|   - Telemetry points ingested per second (target SLA: > 500 pts/sec)    |
|   - In-batch deduplication discard rates                                |
|   - Offline WAL replay batch sizes and backlog depth                    |
|   - Hub authentication cache hit vs miss ratios                         |
+-------------------------------------------------------------------------+
| HTTP & API Latencies:                                                   |
|   - P50, P95, P99 request latencies per route                           |
|   - Downsampling query durations (target SLA: < 300ms PG / < 1000ms SQ) |
|   - HTTP 4xx (client error) and 5xx (server error) rates                |
|   - Rate limiting throttle events (slowapi 429 counts)                  |
+-------------------------------------------------------------------------+
| Database & Host Health:                                                 |
|   - Database connection pool utilization (active, idle, overflow)      |
|   - SQLite busy handler wait durations and WAL checkpoint file sizes    |
|   - Host RAM consumption against 500M systemd MemoryMax limit           |
|   - Raspberry Pi CPU temperature, throttled flags, and SD card I/O wait  |
+-------------------------------------------------------------------------+
```

---

## 3. APM, Health Probes & Liveness Verification

### Health Probe Implementation (`server/app/main.py`)
HubGate V5 provides unauthenticated health endpoints at `/health` and `/api/health`:
```python
@api.get("/health")
@api.get("/api/health")
def health_check():
    db_status = "up"
    try:
        from databasev5 import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "up"
        finally:
            db.close()
    except Exception:
        db_status = "down"
    return {"status": "ok", "db": db_status}
```

### Architectural Deficits of Current Health Probes
1. **Shallow Database Assertion**: `SELECT 1` validates read connectivity only. In SQLite WAL environments, write locks can deadlock ingestion (`database is locked`) while `SELECT 1` continues to succeed. The probe does not test write capability.
2. **Missing Component Validation**: The health endpoint does not verify:
   - Presence sweeper background task liveness (`evaluate_device_presence_batch`).
   - Scheduler worker thread status (`scheduler_lifespan`).
   - Disk space headroom (failure when disk exceeds 95%).
   - Database connection pool availability.
3. **No Liveness vs Readiness Separation**: Kubernetes or systemd cannot distinguish between a process that is initializing (not ready to accept traffic) versus a deadlocked process that must be restarted.
4. **Absence of Distributed Tracing**: Transactions lack W3C TraceContext headers (`traceparent`, `tracestate`). Telemetry originating at an ESP8266 node traversing Mosquitto, HubBrain, Nginx, FastAPI, and PostgreSQL cannot be traced as a continuous unit.

---

## 4. Alert Routing & Notification Dispatching

### Current Passive Alert Lifecycle
The SMSB alerting system operates as a passive database-driven model:

```
[Edge Telemetry Ingest]
         |
         v
[evaluate_device_thresholds] -----> Writes record to `event_log` in DB
         |                          (Severity: CRITICAL, WARNING, INFO)
         v
[evaluate_device_presence] -------> Writes `DEVICE_OFFLINE` to `event_log`
```

Alert rows are queried on-demand by the web dashboard (`GET /api/alerts` via TanStack Query polling at 3000ms intervals).

### The External Dispatch Void
The platform possesses **no external notification transport**:
- **No Webhook Integration**: No outbound HTTP dispatchers to external incident management systems.
- **No Messaging Integrations**: No Telegram Bot API, Slack incoming webhook, Discord, or WhatsApp bridge.
- **No Paging or SMS**: No Twilio, AWS SNS, or SMTP email notification transport.

### Operational Safety Risk
In electrical ATS (Automatic Transfer Switch) environments, physical failures represent immediate life-safety and operational hazards:
- Utility mains failure (`MAINS_FAIL`).
- Generator failing to crank (`GEN_START_FAIL`).
- Phase voltage unbalance or floating ground condition.
- Critical server room thermal runaway (`TEMP_HIGH_CRITICAL`).

Under the current passive architecture, if an operator is not actively staring at an open browser tab running the SMSB dashboard, a catastrophic generator trip or thermal runaway event will go completely unnoticed until equipment fails.

---

## 5. Required Observability Target Architecture

To achieve enterprise production grade, the observability stack requires:

1. **Structured Logging**: Pin `python-json-logger` in `server/requirements.txt`, configure JSON output on stdout, and ingest logs into Grafana Loki via Vector or Promtail.
2. **Prometheus Metrics Pipeline**: Mount `prometheus-fastapi-instrumentator` on `/metrics`, exporting latency histograms, connection pool status, and ingestion throughput.
3. **Hardware & Edge Exporters**: Deploy `node_exporter` on the VPS and Raspberry Pi to track memory, disk I/O, and CPU load.
4. **Active Alert Dispatcher Worker**: A background worker in FastAPI that queries unnotified `CRITICAL` records in `event_log` and dispatches immediate notifications to a configured Telegram channel or webhook endpoint with exponential backoff and deduplication.
