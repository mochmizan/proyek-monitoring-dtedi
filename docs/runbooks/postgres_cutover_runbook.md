# HubGate V5: PostgreSQL 16 Production Cutover Runbook

## Target Environment
- **Host**: Production VPS (`genset@100.108.98.30`)
- **Working Directory**: `/opt/smsb`
- **Python Virtualenv**: `/opt/smsb/venv`
- **Source Database**: SQLite 3 WAL mode (`/opt/smsb/server/hubgatev5.db`)
- **Target Database**: PostgreSQL 16 (`smsb_prod` on `127.0.0.1:5432`)
- **Target Connection**: `postgresql+psycopg2://smsb:<POSTGRES_PASSWORD>@127.0.0.1:5432/smsb_prod`
- **Expected Maintenance Window**: $\le 3\text{ minutes}$ total service downtime (data streaming $\approx 30\text{–}90\text{ seconds}$).

---

## 1. Overview & Architecture Transition

```
Before Cutover (SQLite Single-Writer):
[Edge Hub / ATS] --> [Uvicorn Worker] --> [hubgatev5.db (WAL)]
                                                 |
                                         (Write Lock Contention)

After Cutover (PostgreSQL 16 Multi-Writer MVCC):
[Edge Hub / ATS] --> [Uvicorn Worker] --> [Hikari / SQLAlchemy Pool (20 conns)]
                                                 |
                                         [PostgreSQL 16 Engine]
                                         - MVCC Multi-Writer
                                         - 15s Statement Timeout
                                         - 5s Connect Timeout
```

---

## 2. Pre-Flight Verification & Health Checks

Run these commands on the production VPS prior to scheduling the cutover window:

```bash
# 1. Verify PostgreSQL 16 service is active
sudo systemctl status postgresql

# 2. Test PostgreSQL authentication & connectivity
psql -U smsb -d smsb_prod -h 127.0.0.1 -c "SELECT version();"

# 3. Verify psycopg2 availability in application virtualenv
/opt/smsb/venv/bin/python -c "import psycopg2; print('psycopg2 version:', psycopg2.__version__)"

# 4. Check disk space headroom (ensure >= 5GB free for index builds and VACUUM)
df -h /

# 5. Apply PostgreSQL 16 4GB RAM / 2 Worker VPS Engine Tuning (SMSB 4GB profile on 8GB host with CTFd co-tenancy)
# Configures memory bounds, worker processes, and high-throughput append-only autovacuum
sudo bash -c 'cat << "EOF" > /etc/postgresql/16/main/conf.d/99-smsb-tuning.conf
# SMSB HubGate V5: PostgreSQL 16 4GB VPS Engine Tuning
# 25% of 4GB RAM dedicated to shared buffer pool
shared_buffers = 1GB
effective_cache_size = 3GB
maintenance_work_mem = 256MB
work_mem = 16MB
max_worker_processes = 4
max_parallel_workers = 2
max_parallel_workers_per_gather = 1

# Asynchronous WAL commits: absorbs high-frequency telemetry bursts without disk stalls
synchronous_commit = off

# Aggressive autovacuum trigger for append-only telemetry tables (triggers at 5% inserts)
autovacuum_vacuum_insert_scale_factor = 0.05
EOF'

# Reload PostgreSQL to apply tuning parameters
sudo systemctl restart postgresql

# Verify active engine parameters
psql -U smsb -d smsb_prod -h 127.0.0.1 -c "
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW maintenance_work_mem;
SHOW work_mem;
SHOW max_worker_processes;
SHOW max_parallel_workers;
SHOW max_parallel_workers_per_gather;
SHOW synchronous_commit;
SHOW autovacuum_vacuum_insert_scale_factor;
"

# 6. Execute Migration Tool Dry-Run (validates SQLite schemas and data types with 0 writes)
/opt/smsb/venv/bin/python /opt/smsb/tools/migrate_sqlite_to_postgres.py \
  --sqlite /opt/smsb/server/hubgatev5.db \
  --dry-run
```

Ensure the dry-run reports `Result: PASSED` across all 13+ tables before proceeding.

---

## 3. Step-by-Step Live Cutover Execution

### Step 1: WAL Checkpoint & Snapshot Backup (T-0)

Flush any remaining transactions in SQLite's WAL file and take an offline cold backup:

```bash
# Flush WAL to main database file
sqlite3 /opt/smsb/server/hubgatev5.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Create timestamped offline snapshot
BACKUP_DIR="/opt/smsb/backups"
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)

cp /opt/smsb/server/hubgatev5.db "$BACKUP_DIR/hubgatev5_${TS}.db.bak"
[ -f /opt/smsb/server/hubgatev5.db-wal ] && cp /opt/smsb/server/hubgatev5.db-wal "$BACKUP_DIR/hubgatev5_${TS}.db-wal.bak"
ls -lh "$BACKUP_DIR/hubgatev5_${TS}"*
```

### Step 2: Read-Only Freeze (Stop Ingestion)

Stop the FastAPI application service to freeze SQLite writes:

```bash
sudo systemctl stop smsb-api.service

# Confirm no lingering processes hold database file locks
sudo fuser /opt/smsb/server/hubgatev5.db || echo "Database file cleanly released"
```

### Step 3: Target Schema Initialization in PostgreSQL

Ensure PostgreSQL target tables and constraints are initialized:

```bash
cd /opt/smsb/server
export DATABASE_URL="postgresql+psycopg2://smsb:<POSTGRES_PASSWORD>@127.0.0.1:5432/smsb_prod"

# Initialize tables via SQLAlchemy models (must be executed from /opt/smsb/server or with PYTHONPATH=/opt/smsb/server)
/opt/smsb/venv/bin/python -c "
from databasev5 import engine
from modelsv5 import Base
Base.metadata.create_all(bind=engine)
"

# Run Alembic migrations to align version table
/opt/smsb/venv/bin/alembic upgrade head
cd /opt/smsb
```

### Step 4: High-Throughput Streaming Data Migration (`COPY FROM STDIN`)

Execute `tools/migrate_sqlite_to_postgres.py` using PostgreSQL's native streaming `COPY` protocol with secondary index deferral and memory-bounded batching:

```bash
/opt/smsb/venv/bin/python /opt/smsb/tools/migrate_sqlite_to_postgres.py \
  --sqlite /opt/smsb/server/hubgatev5.db \
  --pg "$DATABASE_URL" \
  --batch-size 25000
```

> [!NOTE]
> **Streaming `COPY` Architecture & Zero-OOM Pipeline**:
> 1. **Index Deferral**: The migration tool automatically inspects `pg_indexes` and drops secondary B-Tree and BRIN indexes on telemetry tables (`data_table`, `temperature_data`, `ats_data`) prior to ingestion. Primary composite keys `(data_id, timestamp)` remain intact to enforce partition constraints.
> 2. **Session Optimization**:
>    - `SET session_replication_role = 'replica';` (bypasses foreign key constraint and trigger validation overhead).
>    - `SET synchronous_commit = off;` (asynchronous WAL writes to prevent I/O stalls).
>    - `SET maintenance_work_mem = '256MB';` (accelerates subsequent index rebuilds).
> 3. **Memory-Bounded Streaming**: Iterates SQLite cursors in chunks of 25,000 rows. Data is converted directly into in-memory CSV buffers (`io.StringIO`) and piped via `psycopg2.cursor.copy_expert()`:
>    ```sql
>    COPY "{target_table}" (...) FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '\N')
>    ```
>    Peak memory footprint remains strictly under **45MB RAM**, completely eliminating OOM crash risk on the 1GB VPS.
> 4. **Partition Auto-Routing**: Data is streamed directly into parent partition heads (`data_table`, `temperature_data`, `ats_data`). PostgreSQL 16's declarative range partitioning automatically routes incoming tuples into their respective monthly child partitions (`data_table_y2026m08`, `data_table_y2026m09`, etc.) based on row timestamps.
> 5. **Index Reconstruction**: Dropped secondary B-Tree indexes and BRIN indexes (`pages_per_range=32, autosummarize=True`) are rebuilt across the table hierarchy in a single sequential heap scan pass.
> 6. **Sequence Alignment & Finalization**:
>    - Sequences are synchronized via `SELECT setval(pg_get_serial_sequence(tbl, col), coalesce(max(id), 1), true)`.
>    - `SET session_replication_role = 'origin';` is restored.
>    - Executes `VACUUM ANALYZE` to update query planner statistics and summarize BRIN ranges.
>    - Computes and prints row parity report between SQLite and PostgreSQL.

**Acceptance Check**:
Verify that the output table displays `MATCH` for all tables, showing 100% row parity, and concludes with `Result: PASSED`.

### Step 5: Switch Application Environment to PostgreSQL

Update `/opt/smsb/server/.env` to point to PostgreSQL:

```bash
# Backup existing .env
cp /opt/smsb/server/.env /opt/smsb/server/.env.sqlite.bak

# Update or append DATABASE_URL and pool configuration
sed -i 's|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://smsb:<POSTGRES_PASSWORD>@127.0.0.1:5432/smsb_prod|' /opt/smsb/server/.env

# Ensure production environment variables are configured
cat << 'EOF' >> /opt/smsb/server/.env

# --- PostgreSQL Production Pool Settings (Phase 4.2) ---
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=10
DB_POOL_RECYCLE=1800
DB_CONNECT_TIMEOUT=5
DB_STATEMENT_TIMEOUT_MS=15000
EOF

# Lock down file permissions
chmod 600 /opt/smsb/server/.env
```

### Step 6: Start API Service & Health Probe

```bash
# Start the API service
sudo systemctl start smsb-api.service

# Verify service is running
sudo systemctl status smsb-api.service

# Check recent logs for errors
sudo journalctl -u smsb-api.service -n 50 --no-pager
```

---

## 4. Post-Cutover Verification Checklist

Perform these smoke tests immediately after starting the service:

### A. Health & Database Dialect Probe
```bash
curl -s http://127.0.0.1:8000/api/health | jq .
```
Expected output:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### B. Connection Pool Status Check
```bash
/opt/smsb/venv/bin/python -c "
from databasev5 import engine
print('Pool Dialect:', engine.dialect.name)
print('Pool Size:', engine.pool.size())
print('Pool Timeout:', engine.pool.timeout())
"
```
Expected: `Pool Dialect: postgresql`, `Pool Size: 20`, `Pool Timeout: 10`.

### C. Live Telemetry Ingestion Check
Wait 30 seconds for edge hubs / publishers to deliver readings, then verify that new rows are written into PostgreSQL:
```bash
psql -U smsb -d smsb_prod -h 127.0.0.1 -c "
SELECT 'ats_data' AS table_name, count(*), max(timestamp) FROM ats_data
UNION ALL
SELECT 'temperature_data', count(*), max(timestamp) FROM temperature_data
UNION ALL
SELECT 'event_log', count(*), max(timestamp) FROM event_log;
"
```
Verify that `max(timestamp)` matches current local UTC time.

### D. Range Partitioning & Child Table Verification
Verify that PostgreSQL 16 correctly partitioned the telemetry data and routed incoming records into monthly child tables rather than an unpartitioned heap:

```bash
psql -U smsb -d smsb_prod -h 127.0.0.1 -c "
SELECT 
    parent.relname AS parent_table,
    child.relname AS child_partition,
    pg_get_expr(child.relpartbound, child.oid) AS partition_boundary,
    c.reltuples::bigint AS estimated_rows
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_class c ON child.oid = c.oid
WHERE parent.relname IN ('data_table', 'temperature_data', 'ats_data')
ORDER BY parent.relname, child.relname;
"
```
Verify that:
1. Child partitions exist for current month (`T`), past month (`T-1`), and forward months (`T+1`, `T+2`).
2. Row counts reflect the streamed records distributed by event timestamp.

### E. BRIN Index Verification & Summarization
Confirm that BRIN indexes are active and properly summarized for fast range scans on time-series telemetry:

```bash
psql -U smsb -d smsb_prod -h 127.0.0.1 -c "
SELECT 
    indexrelid::regclass AS index_name,
    indrelid::regclass AS table_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_index
WHERE indexrelid::regclass::text LIKE '%brin%'
ORDER BY indexrelid::regclass::text;
"
```
Confirm that BRIN indexes (`idx_data_table_ts_brin`, `idx_temperature_data_ts_brin`, `idx_ats_data_ts_brin`) exist on both parent tables and child partitions, with compact storage footprints (typically < 128KB per partition).

---

## 5. Instant Rollback Plan (< 60 Seconds)

If unexpected errors occur (e.g. fatal driver mismatch or database connection failure):

```bash
# 1. Stop the application service
sudo systemctl stop smsb-api.service

# 2. Restore previous .env file
cp /opt/smsb/server/.env.sqlite.bak /opt/smsb/server/.env

# 3. Start the application service with SQLite fallback
sudo systemctl start smsb-api.service

# 4. Verify SQLite health
curl -s http://127.0.0.1:8000/api/health | jq .
sudo systemctl status smsb-api.service
```

No data is lost because the SQLite database file `/opt/smsb/server/hubgatev5.db` was preserved in read-only state throughout the cutover.
