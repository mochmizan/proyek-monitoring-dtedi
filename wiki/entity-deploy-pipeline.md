---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md]
sources: [deploy/setup_push_deploy.sh, deploy/smsb-api.service, deploy/AGENTS.md, commit:acd4f00, commit:6bf89e6]
updated: 2026-08-31
---

# Deploy pipeline

Production deploys by `git push prod main` to the bare repo `ssh://genset@100.108.98.30/opt/smsb.git`. The `post-receive` hook resets the work tree at `/opt/smsb`, then (in order): pip-installs `server/requirements.txt` into `/opt/smsb/venv`, rsyncs `server/` into the legacy runtime dir `/opt/smsb/SERVERv5/v5` (the installed systemd unit runs `WorkingDirectory=/opt/smsb/SERVERv5/v5` — pre-rename path; excludes `hubgatev5.db*`, `.env`, `cert.crt`, `__pycache__`, `.pytest_cache`, `static/` so the runtime DB, secrets, and floor-plan uploads are never touched), builds the SPA with nvm Node 22, rsyncs `dist/` to `/var/www/gui-app` with `chmod -R 755`, restarts `smsb-api` via a narrow sudoers rule, and smoke-checks (`/api/auth/me` must 401, SPA must contain `<title>`, service active).

Two facts that bit us once: pushing an updated `setup_push_deploy.sh` does NOT update the installed hook — it must be patched in place at `/opt/smsb.git/hooks/post-receive` (or setup re-run); and until 2026-08-31 the missing rsync step meant backend pushes silently deployed nothing while the SPA looked fresh (the ATS auto-resolve "didn't work" incident).

Nginx terminates TLS on 443 and proxies `/api/` + `/static/` to Uvicorn on `127.0.0.1:8000` (never a public bind). The unit runs as `smsb` with `MemoryMax=500M`, 2 workers.
