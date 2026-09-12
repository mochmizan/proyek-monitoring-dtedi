# smsb — heterogeneous monorepo (justfile)
# Install: winget install Casey.Just  |  cargo install just  |  brew install just
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["bash", "-uc"]

_default:
    @just --list --unsorted

# ── dev ──────────────────────────────────────────────────────────
dev: dev-infra
    @echo "→ launching HubGate + SPA (wraps start_dev.ps1)"
    ./start_dev.ps1

dev-infra:
    docker compose up -d
    @echo "postgres:5432 mosquitto:1883 ready"

# ── quality gates (DOX Verification) ─────────────────────────────
test:
    pytest server/ -q
    python -m pytest hub/test_edge_resilience.py -q

seed-benchmark total_rows="1000000" days="30":
    python tools/seed_benchmark_telemetry.py --total-rows {{total_rows}} --days {{days}} --clean --verify

benchmark duration="15":
    python tools/benchmark_concurrency_stress.py --duration {{duration}}

lint:
    npm --prefix dashboard run lint
    npm --prefix dashboard run build
    bash -n deploy/setup_push_deploy.sh
    bash -n deploy/deploy_production.sh

build:
    npm --prefix dashboard ci
    npm --prefix dashboard run build

# ── firmware ─────────────────────────────────────────────────────
# WEMOS_ATS is canonical ATS bridge (proofed 2026-08-31 dcfeb84)
firmware-check:
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_TS
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_AC
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_ATS

# ── deploy (no auto-push; use --dry-run first) ───────────────────
deploy-dry-run:
    bash deploy/setup_push_deploy.sh --dry-run

verify base_url="https://10.33.102.10":
    python tools/verify_production_deployment.py --base-url {{base_url}}

