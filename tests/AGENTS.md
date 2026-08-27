# AGENTS.md — tests

## Purpose

Repo-level E2E and verifier tests — offline-safe cross-component suite spanning server ingestion, HubBrain behaviors, and deployment verifiers (no Docker/network/PostgreSQL required).

## Ownership

- **tests/** owns cross-component integration tests
- Owned by root AGENTS.md; component-internal tests live beside their component (e.g., `server/test_*.py`)

## Local Contracts

| File | Coverage | Tests |
|---|---|---|
| `test_e2e_pipeline.py` | Mock publisher → HubBrain → HubGate → DB: payload schemas, TS/ATS/AC ingest + alert evaluation, downlink dispatch, WAL FIFO replay (MQTT fully mocked) | 6 |
| `test_verify_production_deployment.py` | `tools/verify_production_deployment.py`: report counting + mocked 7-step flow | 2 |
| `test_verify_prod_env.py` | `tools/verify_prod_env.py`: masking, banned-value logic, env parsing, weak/valid scenarios | 7 |

- `test_e2e_pipeline.py` creates `test_hubgatev5.db` at repo root (gitignored) with placeholder hub keys in-process; all external effects mocked (`TestClient`, monkeypatched MQTT/SSH)
- `test_verify_prod_env.py` embeds real MQTT_PASS/HUB_KEY strings as banned-value fixtures — pre-public sanitization target (see root secrets checklist)

## Work Guidance

- New cross-component behavior belongs here; single-component tests belong next to that component
- Keep suite offline-safe: Docker/network tests must be skipped by default with explicit opt-in marker
- Match style: stdlib + pytest + FastAPI TestClient, no new heavy deps

## Verification

- `pytest` at repo root runs `tests/` + `server/` (107 tests total)

## Child DOX Index

| Path | Scope |
|---|---|
| — | none |
