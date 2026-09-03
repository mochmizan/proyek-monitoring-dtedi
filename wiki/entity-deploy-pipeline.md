---
type: entity
governed_by: AGENTS.md
links: [wiki/entity-hubgate-v5.md, wiki/entity-data-model.md]
sources: [deploy/setup_push_deploy.sh, deploy/smsb-api.service, deploy/AGENTS.md, commit:acd4f00, commit:6bf89e6]
updated: 2026-09-03
---

# Deploy pipeline

Production deploys by `git push prod main` to the bare repo `ssh://genset@100.108.98.30/opt/smsb.git`. The `post-receive` hook resets the work tree at `/opt/smsb`, then (in order): pip-installs `server/requirements.txt` into `/opt/smsb/venv`, builds the SPA with nvm Node 22, rsyncs `dist/` to `/var/www/gui-app` with `chmod -R 755`, restarts `smsb-api` via a narrow sudoers rule, and smoke-checks (`/api/auth/me` must 401, SPA must contain `<title>`, service active). Runtime server code executes directly from `/opt/smsb/server` (`smsb-api.service` with `WorkingDirectory=/opt/smsb/server`; legacy path `/opt/smsb/SERVERv5/v5` and intermediate rsync block fully decommissioned on 2026-09-03).

Operational history: pushing an updated `setup_push_deploy.sh` does NOT update the installed hook — it must be patched in place at `/opt/smsb.git/hooks/post-receive` (or setup re-run). Historically, prior to 2026-08-31, the missing rsync step meant backend pushes silently deployed nothing while the SPA looked fresh; on 2026-09-03, the server path was normalized directly to `/opt/smsb/server` with unit daemon-reload, permanently eliminating the legacy rsync overlay step.

Nginx terminates TLS on 443 and proxies `/api/` + `/static/` to Uvicorn on `127.0.0.1:8000` (never a public bind). The unit runs as `smsb` with `MemoryMax=500M`, 2 workers.
