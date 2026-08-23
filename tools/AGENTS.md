# AGENTS.md — tools (ops & dev utilities)

Operational and development utilities: Raspberry Pi deployment/backup, database seeding/reset, telemetry simulation, network sniffing, and environment/deployment verifiers. All are standalone scripts run from the repo root or this directory.

## Ownership

- **tools/**: cross-cutting ops scripts — not part of any runtime service; they act ON `SERVERv5/`, `HUBV5/`, `deploy/`, and live hardware
- Owned by root AGENTS.md for repo-wide rules

## Script Groups

| Group | Scripts | Purpose |
|---|---|---|
| **Pi deploy & services** | `deploy_pi_edge.py`, `install_pi_service.py`, `setup_hubbrain_service.py` | Paramiko/SFTP deploy of HubBrain, systemd unit install/restart |
| **Pi backup** | `backup_hub.sh`, `run_pi_backup.py` | Mandatory backup gate: tar `/etc` networking + `.env`/certs/WAL cache, SHA256 verify, offload (see root `HUB_BACKUP_GUIDE.md`) |
| **DB admin** | `init_postgres_db.py`, `setup_postgres_wsl.sh`, `reset_sqlite_users.py`, `purge_dummy_data.py` | Schema init + user/hub seeding, SQLite user reset, mock-data purge |
| **Seeding / simulation** | `seed_demo_data.py`, `seed_rich_history.py`, `mock_publishers.py`, `stream_live_telemetry.py` | Demo rooms/devices, 30-day synthetic history, MQTT node simulators, live TS streaming |
| **Sniffing / debug** | `sniff_pi.py`, `sniff_pi_mqtt.py`, `send_ac_command.py`, `debug_auth_wsl.py` | Remote MQTT sniff via SSH, AC command injection, auth session debugging |
| **Verification** | `verify_production_deployment.py`, `verify_prod_env.py` | 7-step production smoke test; `.env` auditor (weak-value/entropy checks) |
| **Misc** | `browser_test.mjs`, `generate_mosquitto_passwd.py` | Playwright login flow screenshots; Mosquitto PBKDF2 passwd generator |

## Non-Obvious Facts

- ⚠️ Multiple scripts embed **live credentials** (SSH password, MQTT_PASS, HUB_KEY) as defaults/literals: `deploy_pi_edge.py`, `send_ac_command.py`, `sniff_pi*.py`, `stream_live_telemetry.py`, `seed_demo_data.py`, `install_pi_service.py`, `purge_dummy_data.py`, `run_pi_backup.py`. These are tracked today by explicit decision but are Tier-1 sanitization targets before the repo goes public — see root AGENTS.md secrets checklist
- ⚠️ `setup_postgres_wsl.sh` opens `pg_hba.conf` to `0.0.0.0/0 md5` — WSL dev bootstrap only, never production
- `verify_prod_env.py` is the gate used by `deploy/deploy_production.sh` (`--target server --mode prod`)
- Pi tooling assumes host `10.33.36.81`, user `hubadmin`; override via args where provided (`run_pi_backup.py`)
- Mock publishers speak the real payload schemas (`HUB_NAME`, `DEV_ID`, `DEV_TYPE` discriminated union) on `hs109rs/{ts,ats,ac}/data`

## Work Guidance

- New credential handling must read from env/args with no hardcoded defaults — do not add to the Tier-1 list above
- Destructive scripts (`purge_dummy_data.py`, `reset_sqlite_users.py`) must print what they will affect before executing
- Keep scripts stdlib-first (paramiko allowed for SSH/SFTP); match existing argparse style
- Changes to payload shapes must be mirrored in `mock_publishers.py` and `tests/test_e2e_pipeline.py`

## Verification

- Unit-tested parts: `pytest` covers both verifier scripts via `tests/`
- Manual: each script is invoked standalone; see header comments for usage
