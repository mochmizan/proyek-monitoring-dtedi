# AGENTS.md — deploy (production & staging configs)

Deployment artifacts: the production deploy script and Nginx reverse-proxy configs. Production topology is same-origin: Nginx terminates TLS on 443, serves the built SPA at `/`, proxies `/api/` and `/static/` to Uvicorn on `127.0.0.1:8000`.

## Ownership

- **deploy/**: Nginx configs + production deploy orchestration
- Owned by root AGENTS.md; runtime steps documented in root `PRODUCTION_DEPLOYMENT_GUIDE.md`

## Files

| File | Purpose |
|---|---|
| `deploy_production.sh` | 5-step deploy: (1) `verify_prod_env.py --target server --mode prod` preflight, (2) `npm ci && npm run build` SPA, (3) venv + additive `init_sqlv5.py` migrations, (4) self-signed TLS fallback + Nginx install (expects repo at `/opt/smsb`), (5) `hubgate.service` systemd unit (uvicorn, 4 workers, `127.0.0.1:8000`). Flags: `--skip-env-check`, `--allow-localhost`, `--no-service` |
| `nginx_smsb.conf` | Production: `:80` → 301 HTTPS; `:443` ssl/http2, TLS 1.2/1.3, security headers, 10M upload cap. Routes: `/api/` → `127.0.0.1:8000` (WebSocket upgrade headers); `/static/` → `/opt/smsb/SERVERv5/v5/static/` with `@api_backend` fallback; `/assets/*` immutable 1y; `/` → SPA `dist/index.html` no-cache |
| `nginx_staging_wsl.conf` | WSL staging: `:80` `default_server`; same `/api/` proxy; `/static/` and SPA served from the Windows checkout via `/mnt/c/...` |

## Non-Obvious Facts

- Nginx expects the deployment root at `/opt/smsb` (certs from `SERVERv5/v5/cert.crt|key`, static from `SERVERv5/v5/static/`)
- `SERVERv5/v5/static/` is a **generated** deploy target (SPA copied in by the deploy script) — gitignored
- The staging config hardcodes the Windows checkout path `/mnt/c/Users/Mizan/Documents/smsb/...` — machine-specific, adjust per host
- `deploy_production.sh` is additive-safe: `init_sqlv5.py` migrations are idempotent; re-runs do not wipe data
- Cookies work without CORS because SPA and API share the origin (`SameSite=Lax`)

## Work Guidance

- Any new proxied path must be added to **both** Nginx configs and keep the same-origin property
- Never bind Uvicorn to a public interface — only `127.0.0.1`; Nginx is the sole ingress
- Config changes must be reflected in `PRODUCTION_DEPLOYMENT_GUIDE.md` and verified with `tools/verify_production_deployment.py`

## Verification

- `sudo bash deploy/deploy_production.sh` on the VPS, then `python tools/verify_production_deployment.py --base-url https://<host>`
- Staging: install `nginx_staging_wsl.conf`, run verifier with `--base-url http://localhost --allow-localhost`
