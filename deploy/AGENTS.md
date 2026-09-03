# AGENTS.md — deploy

## Purpose

Production deploy props: Nginx reverse-proxy, systemd units, and push-deploy bootstrap. Same-origin: Nginx terminates TLS on 443, serves SPA at `/`, proxies `/api/` and `/static/` to Uvicorn on `127.0.0.1:8000`.

## Ownership

- **deploy/** owns `nginx_smsb.conf`, `smsb-api.service`, `hubbrain.service`, `setup_push_deploy.sh` (plus staging/journald drop-ins)
- Runtime steps owned by `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`; this dir owns the artifact contracts

## Local Contracts

- **nginx_smsb.conf**: `:80` → 301 `https`; `:443` ssl/http2 TLS 1.2/1.3 certs `/etc/nginx/ssl/smsb.crt|.key`, `charset utf-8;`, expanded gzip (`json/css/js/svg` including `text/javascript` and `application/x-javascript` + `gzip_vary`), security headers `X-Content-Type-Options nosniff` / `X-Frame-Options DENY` / `X-XSS-Protection "1; mode=block"` / `Referrer-Policy strict-origin-when-cross-origin` / modern `Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"`, `client_max_body_size 10M`; routes `/api/` → `127.0.0.1:8000`, `/static/` alias `/opt/smsb/server/static/` with `@api_backend` fallback, `/assets/` immutable 1y, `/` → `/var/www/gui-app` (`try_files → /index.html`, `index.html` no-cache); no HSTS until trusted CA
- **smsb-api.service**: canonical HubGate V5 unit — `User=smsb`, `WorkingDirectory=/opt/smsb/server`, `EnvironmentFile=/opt/smsb/server/.env`, uvicorn via `/opt/smsb/venv` on `127.0.0.1:8000` (2 workers, `--limit-concurrency 50`, `--proxy-headers`), `Restart=always` (5s), `MemoryMax=500M`, `After=network-online.target postgresql.service`, sandbox hardening, `ReadWritePaths=/opt/smsb/server` (SQLite DB in app dir)
- **hubbrain.service**: Pi template — `User=hubadmin`, paths `/home/hubadmin/smsb/...` (swap per header), `After=network-online.target mosquitto.service`, `Restart=always` (10s), `MemoryMax=150M`, same hardening; `ReadWritePaths` covers `edge_cache.db` WAL
- **setup_push_deploy.sh**: one-time root bootstrap — creates bare repo `/opt/smsb.git` with `post-receive` hook. Deploys `refs/heads/main` to `/opt/smsb` via fetch + reset --hard. The systemd unit `smsb-api.service` runs directly from canonical `WorkingDirectory=/opt/smsb/server` (legacy `/opt/smsb/SERVERv5/v5` runtime path and rsync compatibility block decommissioned 2026-09-03). Hook sequence: reset worktree → pip install `venv` from `server/requirements.txt` → `npm ci && npm run build` in dashboard → `rsync dist/` to `/var/www/gui-app` → `systemctl restart smsb-api` → smoke checks (`/api/auth/me` unauthenticated must be 401, SPA `<title>`, service active); overridable via `DEPLOY_USER`/`BARE_REPO`/`WORK_TREE`/`VENV_DIR`/`SPA_DIR`/`WWW_DIR`/`SERVICE_NAME`; flags `--dry-run`/`--yes`; no embedded secrets. Note: pushing an updated `setup_push_deploy.sh` does NOT auto-update `/opt/smsb.git/hooks/post-receive` — setup must be re-run or the hook patched in place.
- Ancillaries: `deploy_production.sh` legacy 5-step (superseded by `smsb-api.service` + push-deploy, do not enable both), `journald.conf.dropin` (`SystemMaxUse=100M`), `nginx_staging_wsl.conf` (`:80` default, `/mnt/c/...` SPA path — machine-specific)
- Ownership is load-bearing: `chown -R genset:smsb /opt/smsb && chmod -R g+rwX /opt/smsb && find /opt/smsb -type d -exec chmod g+s {} + && chown smsb:smsb /opt/smsb/server/hubgatev5.db* /opt/smsb/server/.env` — blanket `genset:genset` breaks SQLite writes

## Work Guidance

- Same-origin invariant: any new proxied path must be added to both `nginx_smsb.conf` and `nginx_staging_wsl.conf`
- Never bind Uvicorn to a public interface — only `127.0.0.1`; Nginx is sole ingress
- Never hardcode secrets in units/scripts — secrets via `EnvironmentFile` (`.env` gitignored) only
- Edit the heredoc in `setup_push_deploy.sh`, never the installed hook in `/opt/smsb.git`; keep hook and script in sync
- Reflect config changes in `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`

## Verification

- `bash -n deploy/setup_push_deploy.sh` (also extract and `bash -n` the quoted heredoc hook)
- Staging: `sudo bash deploy/setup_push_deploy.sh --dry-run`; VPS: `curl -k https://127.0.0.1/api/health` must return `{"status":"ok","db":"up"}`

## Child DOX Index

| Path | Scope |
|---|---|
| — | none |
