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
| **DB admin** | `init_postgres_db.py`, `setup_postgres_wsl.sh`, `reset_sqlite_users.py`, `purge_dummy_data.py` | Schema init + seeding, SQLite user reset, mock-data purge |
| **Seeding / simulation** | `seed_demo_data.py`, `seed_rich_history.py`, `mock_publishers.py`, `stream_live_telemetry.py`, `seed_benchmark_telemetry.py` | Demo rooms/devices, 30-day synthetic history, MQTT node simulators (`hs109rs/{ts,ats,ac}/data`), live TS streaming, 1M row chunked benchmark seeder with index EXPLAIN verification |
| **Sniffing / debug** | `sniff_pi.py`, `sniff_pi_mqtt.py`, `send_ac_command.py`, `debug_auth_wsl.py` | Remote MQTT sniff via SSH, AC command injection, auth debugging |
| **Verification & Benchmarking** | `verify_production_deployment.py`, `verify_prod_env.py`, `benchmark_concurrency_stress.py` | 7-step production smoke test; `.env` auditor; async high-concurrency stress test evaluating 5 hard invariants (read/write/throughput/zero-lock) with Markdown/JSON report export |
| **Misc** | `browser_test.mjs`, `generate_mosquitto_passwd.py` | Playwright headless login→dashboard (needs Vite `:5173`); Mosquitto PBKDF2 passwd |

- Env-driven credentials: `MQTT_PASS`/`HUB_KEY`/`PI_PASSWORD` via env/args, error if missing, no hardcoded live defaults (since `afb9c46`); `verify_prod_env.py` banned-value literals are verifier fixtures only
- Pi tooling defaults to `10.33.36.81` / `hubadmin` — override via args where provided
- `setup_postgres_wsl.sh` opens `pg_hba.conf` to `0.0.0.0/0 md5` — WSL dev bootstrap only, never production

## Work Guidance

- New credential handling must read from env/args with no hardcoded defaults
- Destructive scripts (`purge_dummy_data.py`, `reset_sqlite_users.py`) must print scope before executing
- Keep scripts stdlib-first (paramiko allowed for SSH/SFTP); match existing `argparse` style
- Mirror payload-shape changes in `mock_publishers.py` and `tests/test_e2e_pipeline.py`

## Verification

- `pytest` at root covers verifiers via `tests/test_verify_*.py`
- Manual: scripts are standalone — see header comments for usage

## Child DOX Index

| Path | Scope |
|---|---|
| — | none |
