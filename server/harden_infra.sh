#!/usr/bin/env bash
#
# harden_infra.sh — Infrastructure hardening for the PMSR VPS (ubuntu-alfido)
# =============================================================================
# Addresses the host/infrastructure pentest findings:
#   F-03  — server/.env is world-readable and contains production secrets
#   F-08  — Vite dev server exposed on 0.0.0.0:5173 with raw TypeScript source
#   F-09  — SSH password authentication enabled; weak OS password
#   F-10  — default/weak credentials (app seed users, DB, OS)
#   F-11  — GitHub PAT embedded in a home-directory folder name
#   F-15  — 71 OS packages pending security updates
#   F-18  — Tailscale interface active; ACL must be reviewed
#
# SAFETY MODEL
#   * DRY-RUN by default. Nothing is changed unless you pass --apply.
#   * Every file it edits is backed up to <file>.bak.<timestamp> first.
#   * It NEVER restarts sshd or reboots automatically — it prints the exact
#     command for you to run after you have verified key-based login works.
#   * It only PRINTS reminders for actions that require human judgement
#     (rotating secrets, changing passwords, revoking the PAT).
#
# USAGE
#   ./harden_infra.sh                 # dry-run: show what would change
#   ./harden_infra.sh --apply         # apply the safe, automatic changes
#
# Run as the 'alfido' user; it will use sudo for privileged steps.
# =============================================================================

set -uo pipefail

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

TS="$(date +%Y%m%d_%H%M%S)"
PROJECT_DIR="${PMSR_PROJECT_DIR:-$HOME/proyek-monitoring-dtedi}"
ENV_FILE="$PROJECT_DIR/server/.env"
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-hardening.conf"

c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_grn()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_ylw()   { printf '\033[33m%s\033[0m\n' "$*"; }
c_blu()   { printf '\033[36m%s\033[0m\n' "$*"; }

hdr() { echo; c_blu "========== $* =========="; }

run() {
    # Execute a command, or just print it in dry-run mode.
    if [[ $APPLY -eq 1 ]]; then
        echo "  + $*"
        eval "$@"
    else
        echo "  [dry-run] would run: $*"
    fi
}

backup_file() {
    local f="$1"
    [[ -f "$f" ]] || return 0
    if [[ $APPLY -eq 1 ]]; then
        cp -a "$f" "${f}.bak.${TS}"
        echo "  backed up $f -> ${f}.bak.${TS}"
    else
        echo "  [dry-run] would back up $f -> ${f}.bak.${TS}"
    fi
}

if [[ $APPLY -eq 0 ]]; then
    c_ylw "DRY-RUN MODE — no changes will be made. Re-run with --apply to enforce."
else
    c_red  "APPLY MODE — changes WILL be made. Backups are created with suffix .bak.${TS}"
fi

# -----------------------------------------------------------------------------
# F-03: Lock down server/.env (chmod 600) + warn about secret rotation
# -----------------------------------------------------------------------------
hdr "F-03  Lock down server/.env permissions"
if [[ -f "$ENV_FILE" ]]; then
    CUR_MODE="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '?')"
    echo "  current mode of $ENV_FILE = $CUR_MODE"
    if [[ "$CUR_MODE" != "600" ]]; then
        run "chmod 600 '$ENV_FILE'"
    else
        c_grn "  already 600 — nothing to do"
    fi
    c_ylw "  ACTION REQUIRED (manual): the following secrets were exposed and MUST be rotated:"
    echo  "    - DATABASE_URL password (currently smsb:smsb123)  -> set a strong DB password & update Postgres"
    echo  "    - HUB_KEY (currently rahasia_hub_01_xyz)          -> generate: openssl rand -hex 32"
    echo  "    - CSRF_SECRET                                     -> generate: openssl rand -hex 32"
    echo  "    After rotating, update $ENV_FILE and restart the API service."
else
    c_ylw "  $ENV_FILE not found (set PMSR_PROJECT_DIR if the path differs). Skipping."
fi

# -----------------------------------------------------------------------------
# F-08: Bind the Vite dev server to localhost (or build for production)
# -----------------------------------------------------------------------------
hdr "F-08  Stop exposing the Vite dev server to the network"
c_ylw "  The dev server (vite --host 0.0.0.0) must NOT face the network."
echo  "  Recommended (production): build static assets and serve via Nginx:"
echo  "      cd $PROJECT_DIR/dashboard && npm ci && npm run build"
echo  "      # then serve dashboard/dist via Nginx/Caddy behind TLS"
echo  "  If a dev server is still required, bind it to loopback only:"
echo  "      npm run dev -- --host 127.0.0.1"
echo  "  As a network-level stopgap, block external access to :5173 (see firewall step)."

# -----------------------------------------------------------------------------
# F-09: SSH hardening — disable password auth (key-based only)
# -----------------------------------------------------------------------------
hdr "F-09  SSH hardening (disable password authentication)"
c_red "  PRE-FLIGHT: ensure key-based login works BEFORE disabling passwords,"
c_red "  otherwise you can lock yourself out."
echo  "  Checking for an authorized_keys file..."
if [[ -s "$HOME/.ssh/authorized_keys" ]]; then
    c_grn "  Found $HOME/.ssh/authorized_keys (key-based login appears configured)."
    WRITE_SSHD=1
else
    c_red "  No $HOME/.ssh/authorized_keys found! Add your public key first:"
    echo  "      ssh-copy-id alfido@<host>   # from your workstation"
    c_ylw "  Skipping the automatic sshd change until a key is present."
    WRITE_SSHD=0
fi

if [[ "$WRITE_SSHD" -eq 1 ]]; then
    SSHD_CONTENT=$'# Added by harden_infra.sh (F-09)\nPasswordAuthentication no\nChallengeResponseAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nUsePAM yes'
    if [[ $APPLY -eq 1 ]]; then
        echo "  + writing $SSHD_DROPIN"
        printf '%s\n' "$SSHD_CONTENT" | sudo tee "$SSHD_DROPIN" >/dev/null
        sudo chmod 644 "$SSHD_DROPIN"
        echo "  + validating sshd config"
        sudo sshd -t && c_grn "  sshd config valid." || c_red "  sshd config INVALID — fix before restarting!"
        c_ylw "  NOT restarting sshd automatically. After confirming a NEW key-based"
        c_ylw "  session works, run:   sudo systemctl restart ssh"
    else
        echo "  [dry-run] would write $SSHD_DROPIN with:"
        printf '      %s\n' $SSHD_CONTENT
        echo "  [dry-run] would validate with 'sudo sshd -t' (manual 'systemctl restart ssh' afterwards)"
    fi
fi

# -----------------------------------------------------------------------------
# F-10: Weak / default credentials
# -----------------------------------------------------------------------------
hdr "F-10  Replace weak/default credentials (manual)"
c_ylw "  ACTION REQUIRED (manual) — these cannot be rotated safely by a script:"
echo  "    - OS user 'alfido' password (currently ubuntu123):   passwd alfido"
echo  "    - App seed users admin_*/operator/viewer = *123:"
echo  "        rotate via the app's user-management flow or a password-reset script;"
echo  "        enforce a >=12-char complex policy and must_change_password on first login."
echo  "    - PostgreSQL role 'smsb' password (smsb123):"
echo  "        ALTER ROLE smsb WITH PASSWORD '<strong-random>';  then update DATABASE_URL."

# -----------------------------------------------------------------------------
# F-11: GitHub PAT leaked in a home-directory folder name
# -----------------------------------------------------------------------------
hdr "F-11  Remove leaked GitHub PAT from filesystem"
LEAK_DIR="$(find "$HOME" -maxdepth 1 -type d -name 'ghp_*@github.com' 2>/dev/null | head -n1 || true)"
if [[ -n "$LEAK_DIR" ]]; then
    c_red "  Found a directory whose NAME contains a GitHub PAT:"
    echo  "    $LEAK_DIR"
    c_red "  REVOKE THE TOKEN NOW at https://github.com/settings/tokens (the token is in the name)."
    echo  "  Then rename the directory to remove the secret from the filesystem:"
    SAFE_NAME="$HOME/repo_$(basename "$LEAK_DIR" | sed 's/^ghp_[^@]*@/host_/')"
    run "mv '$LEAK_DIR' '$SAFE_NAME'"
    echo  "  Re-clone using SSH or a credential helper instead of a token-in-URL:"
    echo  "      git remote set-url origin git@github.com:<owner>/<repo>.git"
else
    c_grn "  No ghp_*@github.com directory found in \$HOME — nothing to rename."
    c_ylw "  Still verify no token remains in shell history / git remotes:"
    echo  "      git -C '$PROJECT_DIR' remote -v ; grep -R 'ghp_' ~/.bash_history 2>/dev/null"
fi

# -----------------------------------------------------------------------------
# F-15: OS package updates + unattended-upgrades
# -----------------------------------------------------------------------------
hdr "F-15  Apply OS security updates & enable unattended-upgrades"
run "sudo apt-get update -y"
run "sudo apt-get upgrade -y"
run "sudo apt-get install -y unattended-upgrades"
run "sudo dpkg-reconfigure -f noninteractive unattended-upgrades"
c_ylw "  A kernel update may require a reboot. Reboot during a maintenance window:"
echo  "      sudo needrestart -r a   # or: sudo reboot"

# -----------------------------------------------------------------------------
# Firewall: restrict exposed ports (defense-in-depth for F-04/F-08)
# -----------------------------------------------------------------------------
hdr "Firewall  Restrict inbound ports with ufw (defense-in-depth)"
if command -v ufw >/dev/null 2>&1; then
    echo  "  Plan: allow 22 (SSH) + 443/80 (reverse proxy); deny direct 5173 & 8000 from the network."
    run "sudo ufw allow 22/tcp"
    run "sudo ufw allow 80/tcp"
    run "sudo ufw allow 443/tcp"
    run "sudo ufw deny 5173/tcp"
    run "sudo ufw deny 8000/tcp"
    c_ylw "  Enable the firewall only after confirming the rules (it can drop your session if 22 is wrong):"
    echo  "      sudo ufw enable"
else
    c_ylw "  ufw not installed. Install with: sudo apt-get install -y ufw"
fi

# -----------------------------------------------------------------------------
# F-18: Review Tailscale ACLs
# -----------------------------------------------------------------------------
hdr "F-18  Review Tailscale ACLs (manual)"
if command -v tailscale >/dev/null 2>&1; then
    echo  "  Tailscale status:"
    tailscale status 2>/dev/null | sed 's/^/    /' || true
fi
c_ylw "  ACTION REQUIRED (manual): review the tailnet ACL policy so this node only"
echo  "  exposes the intended services to the intended users/tags. Confirm no broad"
echo  "  'autogroup:members -> *:*' rule grants unintended access."

# -----------------------------------------------------------------------------
hdr "DONE"
if [[ $APPLY -eq 0 ]]; then
    c_ylw "Dry-run complete. Review the above, then re-run with --apply to enforce"
    c_ylw "the automatic steps. Items marked 'ACTION REQUIRED (manual)' are never"
    c_ylw "automated and must be done by hand."
else
    c_grn "Apply complete. Review manual action items above (secret rotation, passwords,"
    c_grn "PAT revocation, sshd restart, ufw enable, reboot for kernel updates)."
fi
