# AGENTS.md — tests (repo-level)

Repository-wide automated suite: end-to-end pipeline tests and unit tests for the deployment tooling. Offline-safe — no Docker, network, or PostgreSQL required (SQLite-backed).

## Ownership

- **tests/**: cross-component integration tests that span SERVERv5 ingestion, HubBrain behaviors, and tools/ verifiers
- Owned by root AGENTS.md for repo-wide rules; component-internal tests live in `SERVERv5/v5/test_*.py`

## Files

| File | Coverage | Tests |
|---|---|---|
| `test_e2e_pipeline.py` | Mock publisher → HubBrain → HubGate → DB loop: payload schemas, TS/ATS/AC ingest + alert evaluation, downlink command dispatch, offline-cache FIFO replay (MQTT fully mocked) | 6 |
| `test_verify_production_deployment.py` | Unit tests of `tools/verify_production_deployment.py`: report counting + fully mocked 7-step flow | 2 |
| `test_verify_prod_env.py` | Unit tests of `tools/verify_prod_env.py`: masking, banned-value logic, env parsing, weak/valid env scenarios | 7 |

## Non-Obvious Facts

- `test_e2e_pipeline.py` creates `test_hubgatev5.db` at the **repo root** (gitignored) and sets placeholder hub keys in-process
- ⚠️ `test_verify_prod_env.py` embeds the project's **real** MQTT_PASS/HUB_KEY strings as banned-value fixtures — a pre-push-public sanitization target listed in the root AGENTS.md secrets checklist
- All external effects are mocked (`TestClient`, monkeypatched MQTT/SSH); tests never touch the live Pi or broker

## Work Guidance

- New cross-component behavior belongs here; single-component tests belong next to the component
- Keep the suite offline-safe: any new test needing Docker/network must be skipped by default with an explicit opt-in marker
- Match existing style: stdlib + pytest + FastAPI TestClient, no new heavy deps

## Verification

- `pytest` at repo root runs this directory plus `SERVERv5/v5` tests (100 total)
