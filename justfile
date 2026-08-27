# smsb — heterogeneous monorepo (justfile)
# Install: winget install Casey.Just  |  cargo install just  |  brew install just
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["bash", "-uc"]

_default:
    @just --list --unsorted

# ── dev ───────────────────────────────────────────────────────
dev: dev-infra
    @echo "→ launching HubGate + SPA (wraps start_dev.ps1)"
    ./start_dev.ps1

dev-infra:
    docker compose up -d
    @echo "postgres:5432 mosquitto:1883 ready"

# ── quality gates (DOX Verification) ─────────────────────────
test:
    pytest -q
    python -m pytest HUBV5/V5/test_edge_resilience.py -q

lint:
    npm --prefix clients/gui-app run lint
    npm --prefix clients/gui-app run build
    bash -n deploy/setup_push_deploy.sh
    bash -n deploy/deploy_production.sh

build:
    npm --prefix clients/gui-app ci
    npm --prefix clients/gui-app run build

# ── firmware ─────────────────────────────────────────────────
firmware-check:
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_TS
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_AC
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_ATS
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/fixed_wemos_mqtt_raspi

# ── deploy (no auto-push; use --dry-run first) ─────────────
deploy-dry-run:
    bash deploy/setup_push_deploy.sh --dry-run

verify base_url="https://10.33.102.10":
    python tools/verify_production_deployment.py --base-url {{base_url}}
