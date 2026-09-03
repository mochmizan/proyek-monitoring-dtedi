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

## 1. Logging Architecture & Structured JSON Tracing

The logging subsystem provides transaction visibility, authentication audits, and distributed failure tracing.

### Structured JSON Logging Middleware (`server/app/core/logging.py`)

HubGate V5 implements `StructuredLoggingMiddleware` mounted in `server/app/main.py`. The middleware leverages standard-library `json` serialization on a dedicated logger (`smsb.access`), completely eliminating external dependencies on `python-json-logger`.

```python
class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Structured JSON request logging middleware.
    Outputs single-line JSON with timestamp, request_id, method, path, status_code, latency_ms, client_ip.
    Attaches X-Request-ID to response headers."""
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            client_ip = get_forwarded_address(request)
            log_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "client_ip": client_ip,
            }
            access_logger.info(json.dumps(log_record))
```

### Key Capabilities & Invariants
- **Request Tracing via `X-Request-ID`**: Propagates `X-Request-ID` across inbound request headers or provisions a fresh UUIDv4. Attaches `X-Request-ID` to the HTTP response headers, allowing client SPAs and edge gateways to correlate front-to-back request lifecycles.
- **Single-Line Machine-Parseable JSON**: Emitted as single-line JSON strings to stdout/journald:
  ```json
  {"timestamp": "2026-09-03T17:15:22.104000+00:00", "request_id": "c7a8b1e4-9d52-4f16-8345-d361b7e42d71", "method": "POST", "path": "/api/iot/batch", "status_code": 200, "latency_ms": 14.85, "client_ip": "127.0.0.1"}
  ```
- **Zero-Dependency Architecture**: Employs standard Python `json.dumps()` with a dedicated `StreamHandler(Formatter("%(message)s"))` configured in `configure_logging()`, avoiding third-party formatting package incompatibilities.
- **Security-Aware IP Extraction**: Uses `get_forwarded_address(request)` to accurately resolve client IP through trusted proxies (`TRUSTED_PROXIES = ["127.0.0.1"]`).
- **CORS Header Exposure**: `X-Request-ID` is explicitly declared in `expose_headers` in `server/app/main.py` CORSMiddleware, allowing the dashboard web application to read transaction IDs for diagnostic display.

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
