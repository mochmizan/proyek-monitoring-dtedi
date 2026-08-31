# AGENTS.md — hub (HubBrain V5)

## Purpose

HubBrain V5 edge gateway on Raspberry Pi 4. Bridges `hs109rs/#` MQTT → HTTPS upstream to HubGate V5, enforces whitelist sync, buffers offline telemetry in bounded WAL (`MAX_PENDING_ROWS=20000` FIFO, `0.35s` pacing), and dispatches downlink commands via dynamic `{hub_name}/{dev_type}/command`. Fleet AP `smsb-iot` at `192.168.72.242`; TLS-pinned upstream (`TLS_CERT_PATH`); `requirements.txt` pinned (`paho-mqtt==2.2.1`, `requests==2.32.3`, `python-dotenv==1.0.1`, `urllib3==2.2.3`).

## Ownership

- **hub/** owns edge: `main.py`, `requirements.txt`, `Dockerfile`, `edge_cache.db` (WAL, gitignored), `.env` (gitignored)
- Counterpart: `server/` (HubGate V5) — hub authenticates as client via `X-Hub-ID`/`X-Hub-Key`
- Root `AGENTS.md` owns global DOX rail, secrets policy, and Fleet AP contract

## Local Contracts

### main.py Threads

- Single-file gateway: 4 background threads + optional interactive CLI on main thread
  - `whitelist sync` — every 30s `GET SERVER_DEVICES_URL` → local `whitelist` set of `DEV_ID` (MAC)
  - `command poller` — every 2s `GET SERVER_COMMANDS_URL` (`/api/hub/commands`) → `derive_command_topic` → `{hub_name}/{dev_type}/command` publish → `POST /delivered` ack
  - `WAL replay` — every 5s (`REPLAY_INTERVAL=5.0s`) FIFO replay of `edge_cache.db` with `REPLAY_PACING_DELAY=0.35s` and `REPLAY_BATCH_SIZE=25`
  - `MQTT loop` — `paho-mqtt` subscribe `MQTT_TOPIC` (default `hs109rs/#`), `on_message` filter + forward
- All loops use bounded timeouts (`timeout=5`) and never block MQTT loop.

### WAL (edge_cache.db)

- SQLite WAL at `EDGE_CACHE_DB_PATH` (default `edge_cache.db`), 7-day TTL, at-least-once replay (server dedup on `(DEV_ID, created_at)` recommended)
- Bounded FIFO: `MAX_PENDING_ROWS=20000` — oldest rows pruned on overflow (enforced since `afb9c46`)
- Forward failure → `INSERT` to WAL; success → `DELETE` after `POST` 200; replay resumes on upstream recovery without blocking live `POST`
- Paced replay: FIFO order, `0.35s` delay between rows, `REPLAY_BATCH_SIZE` cap per cycle
- Replay stamps each payload with `_hub_created_at` epoch (original enqueue `created_at`) before `POST` - server derives `event_time` from it so offline bursts keep capture timestamps (see `server/app/routers/iot.py`)

### Whitelist & Filtering

- `MQTT_TOPIC=hs109rs/#` ingest; `DEV_ID` not in whitelist → drop, log `[FILTER BLOCK]`, throttled report to `POST /api/iot/unapproved`
- Whitelisted telemetry → `POST SERVER_URL` (`/api/iot/telemetry`) with `X-Hub-ID`/`X-Hub-Key` headers
- AC control publishes `{target, action, temp}` (legacy `{AC_NUMBER, AC_COMMAND}`) to `hs109rs/ac/command`; CLI accepts `AC1 ON`/`OFF`/`TEMP 20`

### TLS

- Upstream HTTPS uses `verify=TLS_CERT_PATH` (self-signed `cert.crt` copied from server); invalid cert aborts all upstream calls
- `urllib3` SSL warnings disabled (expected for LAN IP + self-signed cert)
- Startup hard-fails if `MQTT_PASS` or `HUB_KEY` missing or equals weak placeholder unless `ALLOW_INSECURE_DEV_KEYS=true` (local laptop staging only)

### Systemd & Networking

- `wlan0` AP: hidden `smsb-iot` WPA2 at `192.168.72.242/24` via `hostapd` + `dnsmasq` (`/etc/dnsmasq.d/smsb-ap.conf`; main `/etc/dnsmasq.conf` empty) + `wlan0-addr.service` (`After=hostapd.service`: `ip link set wlan0 up` + `ip addr add 192.168.72.242/24`)
- `eth0` only in netplan: `dhcp4: true` + static `10.33.102.10/24` + `via: 10.33.102.254` (campus LAN); never add `wifis:` stanzas (fights hostapd)
- Clock: no RTC battery; `chrony 4.8` client of `10.33.102.172` (`makestep` corrects fake boot timestamps); `timesyncd` disabled; no internet (wall-port LAN only)
- `hubbrain.service` runs `python main.py` headless; `main.py --interactive` for AC CLI; `hub/.env` chmod 600

### Environment (.env)

`MQTT_HOST`, `MQTT_PORT`, `MQTT_USER` (default `hubadmin`), `MQTT_PASS`, `MQTT_TOPIC`, `HUB_ID`, `HUB_KEY`, `SERVER_URL`, `SERVER_DEVICES_URL`, `SERVER_COMMANDS_URL` (derived if unset), `TLS_CERT_PATH`, `EDGE_CACHE_DB_PATH`, `ALLOW_INSECURE_DEV_KEYS`, `REPLAY_BATCH_SIZE` (25), `REPLAY_PACING_DELAY` (0.35s), `REPLAY_INTERVAL` (5.0s), `MAX_PENDING_ROWS` (20000).

## Work Guidance

- Keep WAL bounded — never raise `MAX_PENDING_ROWS` without FIFO prune verification; keep `0.35s` pacing and `REPLAY_BATCH_SIZE` to avoid upstream burst
- Keep serial/MQTT bounded — `char[65]` payloads, `512B` buf in firmware bridge; hub `on_message` must not allocate unbounded or block
- Keep loops non-blocking with `timeout=5`; match log tags `[SYNC ...]` `[FILTER ...]` `[POST ...]` `[CONTROL ...]` `[CACHE ...]` `[REPLAY ...]`
- Cross-check any MQTT topic change against `firmware/**/*.ino` topics and `server/app/routers/iot.py` + `server/app/services/*`
- Never commit `.env`, `edge_cache.db`, `cert.crt`, or real `MQTT_PASS`/`HUB_KEY` — all gitignored
- `m41n` and `brain_of_hub_v5.py` are legacy — do not run; use `main.py`
- `tools/deploy_pi_edge.py` reverse tunnel (`Pi :8000 -> Laptop :8000`) is the only supported local staging path

## Verification

- `pytest hub/test_edge_resilience.py` — WAL FIFO bound, 7-day TTL, paced replay, dynamic `derive_command_topic` dispatch (primary gate)
- `pytest` at repo root — 107 tests (includes `hub` 13)
- Manual: `python main.py` → expect `[SYNC SUCCESS]` then `[POST SUCCESS]` on whitelisted telemetry; `GET /api/devices` with hub headers matches local whitelist
- `bash -n hub/CheckSecv5.sh` (on Pi, Linux) — file perms + TLS cert check

## Child DOX Index

| Path | Scope |
|---|---|
| — | No child docs — `hub/` is a leaf. |
