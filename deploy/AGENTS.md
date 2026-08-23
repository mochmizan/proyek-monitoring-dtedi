# AGENTS.md — deploy (production & staging configs)

Deployment artifacts: the production deploy script, systemd unit templates, git push-to-deploy bootstrap, Nginx reverse-proxy configs, and journald sizing drop-in. Production topology is same-origin: Nginx terminates TLS on 443, serves the built SPA at `/`, proxies `/api/` and `/static/` to Uvicorn on `127.0.0.1:8000`.

## Ownership

- **deploy/**: Nginx configs + production deploy orchestration + systemd unit templates
- Owned by root AGENTS.md; runtime steps documented in root `PRODUCTION_DEPLOYMENT_GUIDE.md`

## Files

| File | Purpose |
|---|---|
| `deploy_production.sh` | 5-step deploy: (1) `verify_prod_env.py --target server --mode prod` preflight, (2) `npm ci && npm run build` SPA, (3) venv + additive `init_sqlv5.py` migrations, (4) self-signed TLS fallback + Nginx install (expects repo at `/opt/smsb`), (5) `hubgate.service` systemd unit (uvicorn, 4 workers, `127.0.0.1:8000`). Flags: `--skip-env-check`, `--allow-localhost`, `--no-service`. **Legacy path** — superseded on the `genset` VPS by `smsb-api.service` + `setup_push_deploy.sh` |
| `smsb-api.service` | Canonical HubGate V5 systemd unit for the `genset` VPS: `User=smsb`, `WorkingDirectory=/opt/smsb/SERVERv5/v5`, `EnvironmentFile=/opt/smsb/SERVERv5/v5/.env`, uvicorn via `/opt/smsb/venv` on `127.0.0.1:8000` (2 workers, `--limit-concurrency 50`, `--proxy-headers`), `Restart=always` (5s), `MemoryMax=500M`, `After=network-online.target postgresql.service`, full sandbox hardening; `ReadWritePaths=/opt/smsb/SERVERv5/v5` because the SQLite DB lives in the app dir. Comment blocks explain each section |
| `hubbrain.service` | HubBrain V5 edge (Raspberry Pi) unit **template**: `User=hubadmin`, explicit `/home/hubadmin/smsb/...` path placeholders documented at top (swap or use `%h`), `After=network-online.target mosquitto.service`, `Restart=always` (10s), `MemoryMax=150M`, same hardening; `ReadWritePaths` points at the dir holding `edge_cache.db` (SQLite WAL) |
| `setup_push_deploy.sh` | One-time VPS bootstrap (run as root on `genset`): creates bare repo `/opt/smsb.git` and installs a `post-receive` hook that on `git push prod main` does: `GIT_WORK_TREE=/opt/smsb git checkout -f` → pip install into `/opt/smsb/venv` (if present) → `npm ci && npm run build` (if node present) → `rsync dist/` to `/var/www/gui-app` → `systemctl restart smsb-api` → smoke checks (`/api/auth/me` unauthenticated must be 401, SPA `<title>` grep, `systemctl is-active`) → prints rollback hint on failure. Flags: `--dry-run` (print, don't execute), `--yes` (skip confirmation). Layout overridable via env: `DEPLOY_USER`, `BARE_REPO`, `WORK_TREE`, `VENV_DIR`, `SPA_DIR`, `WWW_DIR`, `SERVICE_NAME`. No secrets embedded |
| `nginx_smsb.conf` | Production (site `hubgate` on `genset`): `:80` → 301 HTTPS; `:443` ssl/http2, TLS 1.2/1.3, certs `/etc/nginx/ssl/smsb.crt|.key` (self-signed, SANs: public IP + Tailscale IP + genset), gzip (`json/css/js/svg` + `gzip_vary`), security headers (`nosniff`, `X-Frame-Options DENY`, `Referrer-Policy`), 10M upload cap. **No HSTS** — commented line documents when to enable (only after a trusted CA cert). Routes: `/api/` → `127.0.0.1:8000`; `/static/` alias to `/opt/smsb/SERVERv5/v5/static/` with `@api_backend` proxy fallback; `/assets/` immutable 1y cache; `/` → SPA at `/var/www/gui-app` with `try_files → /index.html`; `index.html` no-cache |
| `journald.conf.dropin` | `SystemMaxUse=100M` snippet for the 1 GB VPS; 3-line install instructions in header comments |
| `nginx_staging_wsl.conf` | WSL staging: `:80` `default_server`; same `/api/` proxy; `/static/` and SPA served from the Windows checkout via `/mnt/c/...` |

## Install Order (VPS 'genset', campus-day / VPS-day)

1. Provision: user `smsb`, venv `/opt/smsb/venv`, code at `/opt/smsb`, `.env` at `/opt/smsb/SERVERv5/v5/.env` (mode 600), certs at `/etc/nginx/ssl/smsb.crt|.key`
2. `sudo cp deploy/smsb-api.service /etc/systemd/system/`
3. `sudo cp deploy/journald.conf.dropin /etc/systemd/journald.conf.d/99-smsb-size.conf` (mkdir -p first)
4. `sudo cp deploy/nginx_smsb.conf /etc/nginx/sites-available/hubgate && sudo ln -sf /etc/nginx/sites-available/hubgate /etc/nginx/sites-enabled/ && sudo nginx -t`
5. `sudo systemctl daemon-reload` (after ALL unit/dropin installs)
6. `sudo systemctl enable --now smsb-api`
7. `sudo systemctl restart nginx`
8. `sudo bash deploy/setup_push_deploy.sh` (or `--dry-run` first)
9. From each Windows dev machine **on the tailnet**: `git remote add prod ssh://genset@100.108.98.30/opt/smsb.git` — the Tailscale IP (100.108.98.30) resolves only from tailnet devices; use the public IP for non-tailnet access
10. Deploy: `git push prod main`; watch: `ssh genset@100.108.98.30 'journalctl -u smsb-api -f'`

Pi (edge): install `hubbrain.service` per its header (diff against the existing live `hubbrain.service` first), then `daemon-reload` → `enable --now`. Mandatory backup gate (`tools/backup_hub.sh`) before any Pi change.

## Non-Obvious Facts

- Nginx expects the deployment root at `/opt/smsb` (static uploads from `SERVERv5/v5/static/`), but the SPA is served from `/var/www/gui-app` (rsync target of the push-deploy hook) — not from `clients/gui-app/dist` anymore
- `SERVERv5/v5/static/` is a **generated** deploy target — gitignored
- The staging config hardcodes the Windows checkout path `/mnt/c/Users/Mizan/Documents/smsb/...` — machine-specific, adjust per host
- `deploy_production.sh` is additive-safe (`init_sqlv5.py` idempotent) but installs a legacy `hubgate.service` with 4 workers — on `genset` prefer `smsb-api.service`; do not enable both units simultaneously
- Cookies work without CORS because SPA and API share the origin (`SameSite=Lax`)
- The push-deploy hook only deploys `refs/heads/main`; other branch pushes are acknowledged but not deployed
- The hook's smoke check expects **401** (not 000/403) from unauthenticated `/api/auth/me` — a 000 means nginx/uvicorn is down, not auth working

## Work Guidance

- Any new proxied path must be added to **both** Nginx configs and keep the same-origin property
- Never bind Uvicorn to a public interface — only `127.0.0.1`; Nginx is the sole ingress
- Never hardcode secrets in unit files or scripts — secrets flow exclusively through `EnvironmentFile` (`.env`, gitignored)
- Config changes must be reflected in `PRODUCTION_DEPLOYMENT_GUIDE.md` and verified with `tools/verify_production_deployment.py`
- `setup_push_deploy.sh` and its generated hook must stay in sync: edit the heredoc in the setup script, never the installed hook

## Verification

- `bash -n deploy/setup_push_deploy.sh` must pass (hook body is a quoted heredoc — also extract and `bash -n` it)
- VPS: `sudo bash deploy/setup_push_deploy.sh --dry-run` before applying; then `python tools/verify_production_deployment.py --base-url https://<host>`
- Staging: install `nginx_staging_wsl.conf`, run verifier with `--base-url http://localhost --allow-localhost`
