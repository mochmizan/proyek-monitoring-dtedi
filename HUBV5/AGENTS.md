# AGENTS.md — HUBV5 (HubBrain V5 Edge Gateway)

Raspberry Pi 4 edge gateway ("satpam" local): filters IoT node traffic via MQTT, enforces an authenticated whitelist, forwards clean telemetry upstream to HubGate V5 over HTTPS with strict TLS verification, and delivers downlink commands to nodes. Code lives in `HUBV5/V5/`.

## Ownership

- **HUBV5/**: edge gateway source — MQTT bridge, whitelist sync, command poller, AC control CLI, security script
- Owned by root AGENTS.md for repo-wide rules and the DOX framework
- Counterpart: `SERVERv5/` (cloud HubGate V5) — this hub is its authenticated client

## Commands (run from `HUBV5/V5/` on the Pi, venv active)

| Command | What it does |
|---|---|
| `python main.py` | Run gateway (headless daemon mode) |
| `python main.py --interactive` | Run with AC-control CLI in terminal |
| `bash CheckSecv5.sh` (Linux) | Local security audit (file permissions, TLS) |
| `python m41n` | LEGACY script — do not run; see Non-Obvious Facts |

## Stack

Python 3.10+ (Raspberry Pi OS), paho-mqtt 2.x, requests, python-dotenv. `requirements.txt` in `V5/`. Local broker: Mosquitto with `allow_anonymous false` + password file.

## Architecture

- Single file `main.py`: 4 background threads — whitelist sync (30s), fast command polling (2s interval for sub-2-second latency), offline cache FIFO replay (5s), MQTT loop — plus optional interactive AC CLI on the main thread
- **Edge filtering**: MQTT messages on `MQTT_TOPIC` (default `hs109rs/#`) whose `DEV_ID` (MAC) is not in the synced whitelist are dropped, logged as `[FILTER BLOCK]`, and throttled-reported to `/api/iot/unapproved`.
- **Forwarding & Offline Cache**: whitelisted telemetry is POSTed to `SERVER_URL` with `X-Hub-ID`/`X-Hub-Key` headers and `verify=TLS_CERT_PATH`. On forward failure, payloads are buffered in local SQLite WAL (`edge_cache.db`).
- **Paced Replay**: background daemon replays buffered records in FIFO order with pacing delay upon upstream recovery, while live telemetry continues forwarding without backlog queueing.
- **Dynamic Command Dispatch**: polls `SERVER_COMMANDS_URL` (`/api/hub/commands`), resolves topic dynamically via `derive_command_topic` (`{hub_name}/{dev_type}/command`), publishes payload to local MQTT, and acks delivery via `/delivered`.
- **AC control**: publishes standard `{target, action, temp}` (and legacy `{AC_NUMBER, AC_COMMAND}`) JSON to `hs109rs/ac/command`; CLI accepts `AC1 ON`, `AC1 OFF`, `AC1 TEMP 20`.

## Environment (.env in `V5/`)

`MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS`, `MQTT_TOPIC`, `HUB_ID`, `HUB_KEY`, `SERVER_URL`, `SERVER_DEVICES_URL`, `SERVER_COMMANDS_URL` (derived if unset), `TLS_CERT_PATH`, `EDGE_CACHE_DB_PATH` (default `edge_cache.db`), `ALLOW_INSECURE_DEV_KEYS` (set `true` for local laptop staging), `REPLAY_BATCH_SIZE` (default 25), `REPLAY_PACING_DELAY` (default 0.35s), `REPLAY_INTERVAL` (default 5.0s).

## Non-Obvious Facts

- `main.py` supports `ALLOW_INSECURE_DEV_KEYS=true` for local laptop VPS staging without blocking on default test keys
- `tools/deploy_pi_edge.py` establishes an SSH reverse tunnel (`Pi :8000 -> Laptop :8000`) for seamless local laptop staging
- `main.py` hard-fails at startup if `MQTT_PASS` or `HUB_KEY` is missing or equals the weak placeholder hash unless `ALLOW_INSECURE_DEV_KEYS=true`
- `m41n` is the old "brain of hub v.5" script without the weak-placeholder guard — superseded by `main.py`, kept as reference; README's `brain_of_hub_v5.py` name matches neither
- Command poller resolves topic dynamically (`hs109rs/ats/command`, `hs109rs/ac/command`, `hs109rs/ts/command`) based on device type in local registry or payload structure
- `MQTT_USER` default is `hubadmin` (main.py) vs `hub_user` (README/legacy) — broker credentials must match what Mosquitto actually has
- Cert is a self-signed `cert.crt` copied from the server; invalid certs abort all upstream calls
- Disables `urllib3` SSL warnings — expected, local IP + self-signed cert

## Work Guidance

- Keep whitelist sync / poll / forward loops non-blocking with bounded timeouts (`timeout=5`)
- Never commit real `MQTT_PASS`/`HUB_KEY` values — they're secrets in `.env` (chmod 600 on Linux)
- Match existing logging style: `[SYNC ...]`, `[FILTER ...]`, `[POST ...]`, `[CONTROL ...]`, `[CACHE ...]`, `[REPLAY ...]` tags
- Changes touching MQTT topics must be cross-checked against firmware `.ino` topics and `SERVERv5` schemas

## Verification

- `pytest HUBV5/V5/test_edge_resilience.py` for edge offline caching, FIFO replay, and dynamic topic dispatch tests
- Manual: run `python main.py`, watch logs for `[SYNC SUCCESS]` and successful `[POST SUCCESS]` on telemetry
- Cross-check whitelist sync via `GET /api/devices` against `SERVERv5` (hub auth headers required)

