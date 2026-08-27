# smsb â€” heterogeneous monorepo (justfile)
# Install: winget install Casey.Just  |  cargo install just  |  brew install just
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["bash", "-uc"]

_default:
    @just --list --unsorted

# â”€â”€ dev â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
dev: dev-infra
    @echo "â†’ launching HubGate + SPA (wraps start_dev.ps1)"
    ./start_dev.ps1

dev-infra:
    docker compose up -d
    @echo "postgres:5432 mosquitto:1883 ready"

# â”€â”€ quality gates (DOX Verification) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
test:
    pytest -q
    python -m pytest hub/test_edge_resilience.py -q

lint:
    npm --prefix apps/web run lint
    npm --prefix apps/web run build
    bash -n deploy/setup_push_deploy.sh
    bash -n deploy/deploy_production.sh

build:
    npm --prefix apps/web ci
    npm --prefix apps/web run build

# â”€â”€ firmware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Note: WEMOS_ATS is a deprecated alias shim (see firmware/WEMOS_ATS/README.md); only 3 canonical ESP dirs compile.
firmware-check:
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_TS
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/WEMOS_AC
    arduino-cli compile --fqbn esp8266:esp8266:d1_mini firmware/fixed_wemos_mqtt_raspi

# â”€â”€ deploy (no auto-push; use --dry-run first) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
deploy-dry-run:
    bash deploy/setup_push_deploy.sh --dry-run

verify base_url="https://10.33.102.10":
    python tools/verify_production_deployment.py --base-url {{base_url}}
