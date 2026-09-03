#!/usr/bin/env python3
"""
tools/rotate_credentials.py

Production-grade credential rotation CLI utility for SMSB (Smart Monitoring System for Buildings).
Rotates:
  - HubGate V5 Web Users (admin, operator, viewer) with Argon2id hashing
  - Edge-to-Server Gateway Auth Token (HUB_KEY, 64-char hex)
  - Database records (SQLite or PostgreSQL)
  - Server .env configuration file

Usage:
  # Dry run (generate and display without writing to DB or disk)
  python tools/rotate_credentials.py --dry-run

  # Rotate credentials in SQLite database and update server/.env
  python tools/rotate_credentials.py --target-db server/hubgatev5.db --update-env server/.env

  # Preserve dev logins (admin123/operator123/viewer123) for local testing
  python tools/rotate_credentials.py --keep-dev-logins --target-db server/hubgatev5.db

  # Rotate credentials in production PostgreSQL
  python tools/rotate_credentials.py --target-db postgresql://user:pass@host:5432/dbname --update-env /opt/smsb/server/.env
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sqlite3
import string
import uuid
from typing import Callable


# -----------------------------------------------------------------------------
# 1. Hashing Provider (Argon2id)
# -----------------------------------------------------------------------------
def get_argon2_hasher() -> Callable[[str], str]:
    """
    Returns an Argon2id hashing function using either argon2-cffi or passlib.
    """
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        return ph.hash
    except ImportError:
        pass

    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
        return pwd_context.hash
    except ImportError:
        pass

    raise RuntimeError(
        "Neither 'argon2-cffi' nor 'passlib[argon2]' is installed in the current Python environment.\n"
        "Install via: pip install argon2-cffi"
    )


# -----------------------------------------------------------------------------
# 2. Secret & Password Generators
# -----------------------------------------------------------------------------
DEV_CREDENTIALS = {
    "admin": {
        "password": "admin123",
        "display_name": "System Administrator",
        "role": "admin",
    },
    "operator": {
        "password": "operator123",
        "display_name": "Facilities Operator",
        "role": "operator",
    },
    "viewer": {
        "password": "viewer123",
        "display_name": "Guest Viewer",
        "role": "viewer",
    },
}

DEFAULT_USER_METADATA = {
    "admin": {"display_name": "System Administrator", "role": "admin"},
    "operator": {"display_name": "Facilities Operator", "role": "operator"},
    "viewer": {"display_name": "Guest Viewer", "role": "viewer"},
}


def generate_secure_password(length: int = 24) -> str:
    """
    Generates a cryptographically secure random password containing uppercase,
    lowercase, digits, and special characters.
    """
    special_chars = "!@#$%^&*-_=+"
    alphabet = string.ascii_letters + string.digits + special_chars
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in special_chars for c in pw)
        ):
            return pw


def generate_hub_key() -> str:
    """
    Generates a cryptographically secure 64-character hexadecimal token (32 bytes).
    """
    return secrets.token_hex(32)


# -----------------------------------------------------------------------------
# 3. .env File Modifier
# -----------------------------------------------------------------------------
def update_env_file(file_path: str, key_values: dict[str, str], dry_run: bool = False) -> list[str]:
    """
    Updates or appends key-value pairs in a .env file while preserving existing comments.
    Returns a list of human-readable action summaries.
    """
    actions = []
    lines: list[str] = []
    existing_keys: set[str] = set()

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_lines: list[str] = []
    for line in lines:
        matched = False
        for k, v in key_values.items():
            pattern = rf"^(\s*(?:export\s+)?{re.escape(k)}\s*=\s*)(.*)$"
            m = re.match(pattern, line)
            if m:
                prefix = m.group(1)
                updated_lines.append(f"{prefix}{v}\n")
                existing_keys.add(k)
                actions.append(f"Updated {k} in '{file_path}'")
                matched = True
                break
        if not matched:
            updated_lines.append(line)

    for k, v in key_values.items():
        if k not in existing_keys:
            if updated_lines and not updated_lines[-1].endswith("\n"):
                updated_lines.append("\n")
            updated_lines.append(f"{k}={v}\n")
            actions.append(f"Added {k} to '{file_path}'")

    if not dry_run:
        parent = os.path.dirname(os.path.abspath(file_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(updated_lines)

    return actions


# -----------------------------------------------------------------------------
# 4. Database Rotation Handlers (SQLite & PostgreSQL)
# -----------------------------------------------------------------------------
def rotate_sqlite(
    db_path: str,
    users_data: dict[str, dict[str, str]],
    new_hub_key: str,
    target_hub_id: str,
    dry_run: bool,
) -> list[str]:
    """
    Applies credential updates, clears active sessions, and updates hub_table in SQLite.
    """
    reports = []
    if not os.path.exists(db_path):
        reports.append(f"[WARN] SQLite file '{db_path}' not found. Skipping DB updates.")
        return reports

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # 1. Update Users
        for username, udata in users_data.items():
            pw_hash = udata["hash"]
            display_name = udata["display_name"]
            role = udata["role"]

            exists = cur.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                if not dry_run:
                    cur.execute(
                        "UPDATE users SET password_hash = ?, display_name = ?, role = ?, "
                        "failed_login_attempts = 0, lockout_until = NULL WHERE username = ?",
                        (pw_hash, display_name, role, username),
                    )
                reports.append(f"[DB] Updated password hash and reset lockouts for user '{username}' ({role})")
            else:
                if not dry_run:
                    cur.execute(
                        "INSERT INTO users (id, username, password_hash, display_name, role, "
                        "failed_login_attempts, created_at) VALUES (?, ?, ?, ?, ?, 0, datetime('now'))",
                        (str(uuid.uuid4()), username, pw_hash, display_name, role),
                    )
                reports.append(f"[DB] Created new user '{username}' ({role})")

        # 2. Invalidate Sessions and Reset Login Attempts
        if not dry_run:
            cur.execute("DELETE FROM sessions")
            cur.execute("DELETE FROM login_attempts")
        reports.append("[DB] Flushed active user sessions and cleared login attempt counters")

        # 3. Update HUB_KEY in hub_table
        table_exists = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hub_table'"
        ).fetchone()
        if table_exists:
            hubs = cur.execute("SELECT hub_id, hub_name FROM hub_table").fetchall()
            matched_hubs = []
            for h_id, h_name in hubs:
                if target_hub_id == "all" or h_id == target_hub_id:
                    matched_hubs.append(h_id)
                    if not dry_run:
                        cur.execute("UPDATE hub_table SET hub_key = ? WHERE hub_id = ?", (new_hub_key, h_id))
                    reports.append(f"[DB] Updated HUB_KEY for hub '{h_id}' ('{h_name}')")

            if not matched_hubs and hubs:
                existing_ids = ", ".join(h[0] for h in hubs)
                reports.append(f"[WARN] Target hub '{target_hub_id}' not found in hub_table. Existing hubs: [{existing_ids}]")
        else:
            reports.append("[WARN] Table 'hub_table' not found in SQLite database.")

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return reports


def rotate_postgres(
    db_url: str,
    users_data: dict[str, dict[str, str]],
    new_hub_key: str,
    target_hub_id: str,
    dry_run: bool,
) -> list[str]:
    """
    Applies credential updates, clears active sessions, and updates hub_table in PostgreSQL via SQLAlchemy.
    """
    reports = []
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        raise RuntimeError("SQLAlchemy is required to rotate PostgreSQL credentials. Install via 'pip install sqlalchemy'.")

    engine = create_engine(db_url)
    with engine.begin() as conn:
        # 1. Update Users
        for username, udata in users_data.items():
            pw_hash = udata["hash"]
            display_name = udata["display_name"]
            role = udata["role"]

            exists = conn.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username},
            ).fetchone()

            if exists:
                if not dry_run:
                    conn.execute(
                        text(
                            "UPDATE users SET password_hash = :hash, display_name = :display_name, "
                            "role = :role, failed_login_attempts = 0, lockout_until = NULL "
                            "WHERE username = :username"
                        ),
                        {
                            "hash": pw_hash,
                            "display_name": display_name,
                            "role": role,
                            "username": username,
                        },
                    )
                reports.append(f"[DB] Updated password hash and reset lockouts for user '{username}' ({role})")
            else:
                if not dry_run:
                    conn.execute(
                        text(
                            "INSERT INTO users (id, username, password_hash, display_name, role, "
                            "failed_login_attempts, created_at) "
                            "VALUES (:id, :username, :hash, :display_name, :role, 0, NOW())"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "username": username,
                            "hash": pw_hash,
                            "display_name": display_name,
                            "role": role,
                        },
                    )
                reports.append(f"[DB] Created new user '{username}' ({role})")

        # 2. Invalidate Sessions and Reset Login Attempts
        if not dry_run:
            conn.execute(text("DELETE FROM sessions"))
            conn.execute(text("DELETE FROM login_attempts"))
        reports.append("[DB] Flushed active user sessions and cleared login attempt counters")

        # 3. Update HUB_KEY in hub_table
        if target_hub_id == "all":
            if not dry_run:
                conn.execute(text("UPDATE hub_table SET hub_key = :hub_key"), {"hub_key": new_hub_key})
            reports.append("[DB] Updated HUB_KEY for all hubs in hub_table")
        else:
            hub_row = conn.execute(
                text("SELECT hub_id, hub_name FROM hub_table WHERE hub_id = :hub_id"),
                {"hub_id": target_hub_id},
            ).fetchone()
            if hub_row:
                if not dry_run:
                    conn.execute(
                        text("UPDATE hub_table SET hub_key = :hub_key WHERE hub_id = :hub_id"),
                        {"hub_key": new_hub_key, "hub_id": target_hub_id},
                    )
                reports.append(f"[DB] Updated HUB_KEY for hub '{target_hub_id}' ('{hub_row[1]}')")
            else:
                reports.append(f"[WARN] Target hub '{target_hub_id}' not found in PostgreSQL hub_table.")

    return reports


# -----------------------------------------------------------------------------
# 5. Handover Runbook Printer
# -----------------------------------------------------------------------------
def print_runbook(hub_key: str, admin_pass: str, operator_pass: str, viewer_pass: str) -> None:
    banner = "=" * 80
    print(f"\n{banner}")
    print(" SMSB CREDENTIAL ROTATION -- OPERATIONAL HANDOVER RUNBOOK")
    print(banner)
    print(
        f"""
STEP 1: CENTRAL SERVER (VPS) VERIFICATION
  1. Confirm server/.env has the newly generated HUB_KEY:
     HUB_KEY={hub_key}
  2. Restart the backend API daemon:
     sudo systemctl restart smsb-api
  3. Verify service is healthy and old sessions are invalidated:
     curl -k https://127.0.0.1:8000/api/auth/me   # Expected: 401 Unauthorized
  4. Log in via web dashboard using:
     - Admin:    admin / {admin_pass}
     - Operator: operator / {operator_pass}
     - Viewer:   viewer / {viewer_pass}

STEP 2: RASPBERRY PI EDGE GATEWAY SYNCHRONIZATION
  Connect to the edge gateway (hubadmin@10.33.102.10 or 10.33.36.81):
  1. Edit /home/hubadmin/hub/.env (or /opt/smsb/hub/.env):
     HUB_KEY={hub_key}
  2. Restart the HubBrain ingestion daemon:
     sudo systemctl restart hubbrain
  3. Check systemd logs to verify edge-to-server sync succeeds:
     journalctl -u hubbrain -n 30 --no-pager | grep "SYNC"

STEP 3: MOSQUITTO MQTT CREDENTIAL ROTATION (IF CHANGING MQTT_PASS)
  1. Generate new Mosquitto PBKDF2 hash on the Pi:
     python3 tools/generate_mosquitto_passwd.py --user hubadmin --password <NEW_MQTT_PASS> --file /etc/mosquitto/passwd
  2. Reload Mosquitto broker:
     sudo systemctl reload mosquitto
  3. Update MQTT_PASS in /home/hubadmin/hub/.env and restart HubBrain:
     sudo systemctl restart hubbrain

STEP 4: ESP8266 FIRMWARE SECRETS (TS / ATS / AC NODES)
  1. Update firmware/<NODE>/secrets.h with the new MQTT_PASS:
     #define MQTT_PASS "<NEW_MQTT_PASS>"
  2. Recompile and reflash nodes using esptool / Arduino CLI / avrdude.

STEP 5: LINUX OPERATING SYSTEM PASSWORDS (SSH)
  1. Rotate VPS SSH user password:
     genset@vps:~$ passwd genset
  2. Rotate Pi SSH user password:
     hubadmin@pi:~$ passwd hubadmin
{banner}
"""
    )


# -----------------------------------------------------------------------------
# 6. Main CLI Orchestration
# -----------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="SMSB Production Credential Rotation Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate credential generation and show SQL/env changes without modifying DB or files.",
    )
    parser.add_argument(
        "--keep-dev-logins",
        action="store_true",
        help="Keep development passwords (admin123, operator123, viewer123) instead of random passwords.",
    )
    parser.add_argument(
        "--target-db",
        default=None,
        help="Path to SQLite DB (e.g. server/hubgatev5.db) or PostgreSQL URL (e.g. postgresql://user:pass@host/db).",
    )
    parser.add_argument(
        "--update-env",
        default=None,
        help="Path to server .env file to update with the new HUB_KEY (e.g. server/.env).",
    )
    parser.add_argument(
        "--hub-id",
        default="hs109rs-hub-01",
        help="Target hub ID in hub_table to update with new HUB_KEY (default: hs109rs-hub-01, or 'all').",
    )
    parser.add_argument(
        "--pass-length",
        type=int,
        default=24,
        help="Length of generated passwords (default: 24 characters).",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database updates entirely (only generate credentials and update .env if requested).",
    )

    args = parser.parse_args()

    print("================================================================================")
    print(" SMSB CREDENTIAL ROTATION UTILITY")
    print("================================================================================")
    if args.dry_run:
        print("[MODE] DRY RUN (No changes will be written to disk or database)\n")

    # Step A: Initialize Hasher
    hasher = get_argon2_hasher()

    # Step B: Generate Web Credentials
    generated_users: dict[str, dict[str, str]] = {}
    if args.keep_dev_logins:
        print("[!] Preserving development logins (--keep-dev-logins)")
        for uname, udata in DEV_CREDENTIALS.items():
            pw = udata["password"]
            h = hasher(pw)
            generated_users[uname] = {
                "password": pw,
                "hash": h,
                "display_name": udata["display_name"],
                "role": udata["role"],
            }
    else:
        print(f"[*] Generating high-entropy secure passwords ({args.pass_length} chars, Argon2id)...")
        for uname, udata in DEFAULT_USER_METADATA.items():
            pw = generate_secure_password(args.pass_length)
            h = hasher(pw)
            generated_users[uname] = {
                "password": pw,
                "hash": h,
                "display_name": udata["display_name"],
                "role": udata["role"],
            }

    # Step C: Generate HUB_KEY
    new_hub_key = generate_hub_key()

    print("\n--- GENERATED CREDENTIALS ---")
    for uname, udata in generated_users.items():
        print(f"User:         {uname:10} (Role: {udata['role']:8})")
        print(f"Display Name: {udata['display_name']}")
        print(f"Password:     {udata['password']}")
        print(f"Hash:         {udata['hash'][:35]}...")
        print("-" * 40)
    print(f"HUB_KEY (64-hex): {new_hub_key}\n")

    # Step D: Update .env if requested
    if args.update_env:
        env_actions = update_env_file(
            args.update_env,
            {"HUB_KEY": new_hub_key},
            dry_run=args.dry_run,
        )
        for act in env_actions:
            prefix = "[DRY-RUN] " if args.dry_run else "[OK] "
            print(f"{prefix}{act}")

    # Step E: Database Updates
    if not args.no_db:
        target_db = args.target_db
        if not target_db:
            env_db = os.environ.get("DATABASE_URL")
            if env_db:
                target_db = env_db
            elif os.path.exists("server/hubgatev5.db"):
                target_db = "server/hubgatev5.db"

        if target_db:
            print(f"\n[*] Target Database: {target_db}")
            # Determine dialect
            if target_db.startswith("postgresql://") or target_db.startswith("postgres://"):
                db_reports = rotate_postgres(
                    target_db,
                    generated_users,
                    new_hub_key,
                    args.hub_id,
                    dry_run=args.dry_run,
                )
            else:
                sqlite_path = target_db
                if sqlite_path.startswith("sqlite:///"):
                    sqlite_path = sqlite_path[len("sqlite:///") :]
                db_reports = rotate_sqlite(
                    sqlite_path,
                    generated_users,
                    new_hub_key,
                    args.hub_id,
                    dry_run=args.dry_run,
                )

            for rep in db_reports:
                prefix = "[DRY-RUN] " if args.dry_run else ""
                print(f"{prefix}{rep}")
        else:
            print("[NOTICE] No target database specified or detected. Skipping database updates.")

    # Step F: Print Operational Runbook
    print_runbook(
        hub_key=new_hub_key,
        admin_pass=generated_users["admin"]["password"],
        operator_pass=generated_users["operator"]["password"],
        viewer_pass=generated_users["viewer"]["password"],
    )


if __name__ == "__main__":
    main()
