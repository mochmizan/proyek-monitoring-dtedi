# AGENTS.md — tools

## Purpose

Ops utilities that act on `server/`, `hub/`, `deploy/`, and live hardware: Pi deploy/backup, DB admin, seeding/simulation, sniffing/debug, and deployment verifiers.

## Ownership

- **tools/** owns all cross-cutting ops scripts — not part of any runtime service
- Owned by root AGENTS.md for repo-wide rules

## Local Contracts

| Group | Scripts | Purpose |
|---|---|---|
| **Pi deploy & services** | `deploy_pi_edge.py`, `install_pi_service.py`, `setup_hubbrain_service.py` | Paramiko/SFTP deploy of HubBrain, systemd unit install/restart |
| **Pi backup** | `backup_hub.sh`, `run_pi_backup.py` | Mandatory backup gate: tar `/etc` networking + `.env`/certs/WAL, SHA256 verify, offload (see `docs/HUB_BACKUP_GUIDE.md`) |
| **DB & Credential Admin** | `init_postgres_db.py`, `setup_postgres_wsl.sh`, `reset_sqlite_users.py`, `rotate_credentials.py`, `purge_dummy_data.py` | Schema init + seeding, SQLite user reset, production credential / HUB_KEY rotation CLI, mock-data purge |
| **Seeding / simulation** | `seed_demo_data.py`, `seed_rich_history.py`, `mock_publishers.py`, `stream_live_telemetry.py`, `seed_benchmark_telemetry.py` | Demo rooms/devices, 30-day synthetic history, MQTT node simulators (`hs109rs/{ts,ats,ac}/data`), live TS streaming, 1M row chunked benchmark seeder with index EXPLAIN verification |
| **Sniffing / debug** | `sniff_pi.py`, `sniff_pi_mqtt.py`, `send_ac_command.py`, `debug_auth_wsl.py` | Remote MQTT sniff via SSH, AC command injection, auth debugging |
| **Verification & Benchmarking** | `verify_production_deployment.py`, `verify_prod_env.py`, `benchmark_concurrency_stress.py` | 7-step production smoke test; `.env` auditor; async high-concurrency stress test evaluating 5 hard invariants (read/write/throughput/zero-lock) with Markdown/JSON report export |
| **Misc** | `browser_test.mjs`, `generate_mosquitto_passwd.py` | Playwright headless login→dashboard (needs Vite `:5173`); Mosquitto PBKDF2 passwd |

- Env-driven credentials: `MQTT_PASS`/`HUB_KEY`/`PI_PASSWORD` via env/args, error if missing, no hardcoded live defaults (since `afb9c46`); `verify_prod_env.py` banned-value literals are verifier fixtures only
- Pi tooling defaults to `10.33.36.81` / `hubadmin` — override via args where provided
- `setup_postgres_wsl.sh` opens `pg_hba.conf` to `0.0.0.0/0 md5` — WSL dev bootstrap only, never production

### Benchmark Tooling & Recipes

- **`tools/seed_benchmark_telemetry.py`**:
  - High-performance synthetic telemetry seeder generating and inserting realistic telemetry rows (500k TS, 500k ATS = 1,000,000 rows across 30 days) using chunked SQLAlchemy Core DML in < 15s (SQLite WAL / PostgreSQL). Validates query plans with EXPLAIN.
  - CLI: `python tools/seed_benchmark_telemetry.py [--total-rows 1000000] [--days 30] [--batch-size 25000] [--db-url URL] [--clean] [--verify]`
  - Recipe: `just seed-benchmark [total_rows] [days]` (default: `1000000`, `30`)
- **`tools/rotate_credentials.py`**:
  - Production CLI utility to rotate HubGate V5 web user credentials (Argon2id hashing), generate 64-char hex HUB_KEY, update SQLite / PostgreSQL databases and server .env files, flush active user sessions, and print operational runbooks.
  - CLI: `python tools/rotate_credentials.py [--dry-run] [--keep-dev-logins] [--target-db PATH_OR_URL] [--update-env PATH] [--hub-id ID]`
  - Runbook documentation: `docs/CREDENTIAL_ROTATION_GUIDE.md`
- **`tools/benchmark_concurrency_stress.py`**:
  - Async multi-worker concurrency stress benchmark executing concurrent write batches (`POST /api/iot/batch`), dashboard polling reads (`GET /api/devices`, `/api/rooms`), and heavy downsampling queries (`GET /api/devices/{id}/history?range=30d`) against HubGate V5 to validate 5 SLAs (read latency P95 < 300ms, batch write latency P95 < 350ms, zero DB locked errors, throughput > 500 pts/sec, bounded room map <= 4 queries). Exports Markdown and JSON reports.
  - CLI: `python tools/benchmark_concurrency_stress.py [--duration 15] [--writers 2] [--readers 3] [--downsample-workers 1] [--batch-size 75] [--base-url URL] [--output-json PATH] [--output-markdown PATH]`
  - Recipe: `just benchmark [duration]` (default: `15`)

## Work Guidance

- New credential handling must read from env/args with no hardcoded defaults
- Destructive scripts (`purge_dummy_data.py`, `reset_sqlite_users.py`) must print scope before executing
- Keep scripts stdlib-first (paramiko allowed for SSH/SFTP); match existing `argparse` style
- Mirror payload-shape changes in `mock_publishers.py` and `tests/test_e2e_pipeline.py`

## Verification

- `just seed-benchmark` — seeds 1,000,000 synthetic rows and verifies index usage.
- `just benchmark` — executes 15s concurrency stress test against SQLite WAL or PostgreSQL.
- `pytest` at root covers verifiers via `tests/test_verify_*.py`
- Manual: scripts are standalone — see header comments for usage

## Child DOX Index

| Path | Scope |
|---|---|
| — | none |
