#!/usr/bin/env python3
"""
tools/verify_prod_env.py - Production Environment Verification Script (Milestone 10)

Inspects production .env configuration files for server (Central Server) and
hub (Edge Gateway). Validates that all required variables are set and asserts
that none match weak defaults, insecure placeholders, or development fallback values.

Usage:
    python tools/verify_prod_env.py [--server-env PATH] [--hub-env PATH] [--mode prod|dev] [--allow-localhost]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


# ==============================================================================
# KNOWN WEAK / PLACEHOLDER PATTERNS
# ==============================================================================
BANNED_SUBSTRINGS = [
    "changeme",
    "placeholder",
    "weak_mqtt_pass",
    "weak_hub_key",
    "strong_local_hub_key",
    "hubadmin_local_secret_pass",
    "your_secret_here",
    "secret_key_here",
    "example.com",
    "todo",
    "plz don't hack",
    "plz dont hack",
]

BANNED_EXACT_VALUES = {
    # Default / trivial passwords
    "password", "admin", "postgres", "root", "123456", "12345678", "secret", "caslie",
    # Known repo template secrets
    "strong_local_hub_key_1234567890abcdef",
    "hubadmin_local_secret_pass_2026",
    "414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1",
    "70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4",
}

BANNED_DB_PASSWORDS = {"postgres", "password", "admin", "root", "123456", "caslie"}


@dataclass
class CheckResult:
    target: str
    variable: str
    status: str  # "PASS", "FAIL", "WARN"
    message: str
    value_preview: str = ""


@dataclass
class VerificationReport:
    mode: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == "WARN")


def mask_secret(value: str) -> str:
    """Mask secret string showing only first and last 3 characters."""
    if not value:
        return "<EMPTY>"
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def parse_env_file(filepath: Path | str) -> dict[str, str]:
    """Parse a .env file into key-value pairs, ignoring comments and blank lines."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found at: {path}")

    env_vars: dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # Remove surrounding quotes if present
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                env_vars[key] = val
    return env_vars


def check_is_banned(value: str) -> str | None:
    """Check if value matches any banned exact strings or substrings."""
    lower_val = value.strip().lower()
    if lower_val in {b.lower() for b in BANNED_EXACT_VALUES}:
        return f"Matches known default/insecure value '{value}'"
    for banned in BANNED_SUBSTRINGS:
        if banned in lower_val:
            return f"Contains insecure placeholder substring '{banned}'"
    return None


# ==============================================================================
# SERVER ENVIRONMENT VERIFICATION
# ==============================================================================
def verify_server_env(
    env_vars: dict[str, str],
    report: VerificationReport,
    mode: str = "prod",
    allow_localhost: bool = False,
) -> None:
    target = "server"

    # 1. DATABASE_URL
    db_url = env_vars.get("DATABASE_URL", "").strip()
    if not db_url:
        report.results.append(CheckResult(
            target=target,
            variable="DATABASE_URL",
            status="FAIL",
            message="DATABASE_URL is missing or empty. A PostgreSQL connection string is required.",
        ))
    else:
        # Check scheme
        if not (db_url.startswith("postgresql://") or db_url.startswith("postgres://") or db_url.startswith("postgresql+psycopg://")):
            if mode == "prod":
                report.results.append(CheckResult(
                    target=target,
                    variable="DATABASE_URL",
                    status="FAIL",
                    message=f"DATABASE_URL scheme must be postgresql:// in production. Found: {db_url.split('://')[0]}://",
                    value_preview=mask_secret(db_url),
                ))
            else:
                report.results.append(CheckResult(
                    target=target,
                    variable="DATABASE_URL",
                    status="WARN",
                    message="Non-standard DB scheme for development.",
                    value_preview=mask_secret(db_url),
                ))
        else:
            # Parse DB URL components
            try:
                parsed = urlparse(db_url)
                db_host = parsed.hostname or ""
                db_pass = parsed.password or ""
                db_name = parsed.path.lstrip("/")

                errors = []
                if mode == "prod" and not allow_localhost and db_host in {"localhost", "127.0.0.1", "::1"}:
                    # If Postgres runs on same VPS, localhost is acceptable if password is strong,
                    # but warning/info should be noted. If password is default, it is a hard fail.
                    if db_pass.lower() in BANNED_DB_PASSWORDS or not db_pass:
                        errors.append(f"PostgreSQL host is localhost with default/insecure password '{db_pass}'")

                if db_pass.lower() in BANNED_DB_PASSWORDS:
                    errors.append(f"Insecure/default database password '{db_pass}' detected")

                banned_reason = check_is_banned(db_url)
                if banned_reason:
                    errors.append(banned_reason)

                if errors:
                    report.results.append(CheckResult(
                        target=target,
                        variable="DATABASE_URL",
                        status="FAIL",
                        message="; ".join(errors),
                        value_preview=mask_secret(db_url),
                    ))
                else:
                    report.results.append(CheckResult(
                        target=target,
                        variable="DATABASE_URL",
                        status="PASS",
                        message=f"Valid PostgreSQL URL (host: {db_host}, db: {db_name})",
                        value_preview=mask_secret(db_url),
                    ))
            except Exception as e:
                report.results.append(CheckResult(
                    target=target,
                    variable="DATABASE_URL",
                    status="FAIL",
                    message=f"Failed to parse DATABASE_URL: {e}",
                    value_preview=mask_secret(db_url),
                ))

    # 2. CORS_ALLOWED_ORIGINS
    cors = env_vars.get("CORS_ALLOWED_ORIGINS", "").strip()
    if cors:
        if "*" in cors and mode == "prod":
            report.results.append(CheckResult(
                target=target,
                variable="CORS_ALLOWED_ORIGINS",
                status="FAIL",
                message="Wildcard '*' in CORS_ALLOWED_ORIGINS is prohibited in production when using cookie authentication.",
                value_preview=cors,
            ))
        elif "http://localhost" in cors and mode == "prod" and not allow_localhost:
            report.results.append(CheckResult(
                target=target,
                variable="CORS_ALLOWED_ORIGINS",
                status="WARN",
                message="CORS contains localhost origins in production mode.",
                value_preview=cors,
            ))
        else:
            report.results.append(CheckResult(
                target=target,
                variable="CORS_ALLOWED_ORIGINS",
                status="PASS",
                message=f"CORS origins configured: {cors}",
                value_preview=cors,
            ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="CORS_ALLOWED_ORIGINS",
            status="PASS",
            message="No CORS origins configured (strict same-origin mode).",
        ))

    # 3. Seed / Gateway credentials if present
    if "HUB_KEY" in env_vars:
        hk = env_vars["HUB_KEY"].strip()
        banned_reason = check_is_banned(hk)
        if banned_reason:
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="FAIL",
                message=f"HUB_KEY: {banned_reason}",
                value_preview=mask_secret(hk),
            ))
        elif len(hk) < 32:
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="FAIL",
                message=f"HUB_KEY is too short ({len(hk)} chars). Minimum 32 hex/character entropy required.",
                value_preview=mask_secret(hk),
            ))
        else:
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="PASS",
                message="HUB_KEY meets entropy requirements (>= 32 chars).",
                value_preview=mask_secret(hk),
            ))


# ==============================================================================
# HUB EDGE GATEWAY ENVIRONMENT VERIFICATION
# ==============================================================================
def verify_hub_env(
    env_vars: dict[str, str],
    report: VerificationReport,
    mode: str = "prod",
    allow_localhost: bool = False,
) -> None:
    target = "hub"

    # 1. MQTT_HOST & MQTT_PORT
    mqtt_host = env_vars.get("MQTT_HOST", "").strip()
    if not mqtt_host:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_HOST",
            status="FAIL",
            message="MQTT_HOST is missing or empty.",
        ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_HOST",
            status="PASS",
            message=f"MQTT broker host: {mqtt_host}",
            value_preview=mqtt_host,
        ))

    mqtt_port = env_vars.get("MQTT_PORT", "").strip()
    if not mqtt_port or not mqtt_port.isdigit():
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_PORT",
            status="FAIL",
            message=f"MQTT_PORT must be a valid integer port number. Found: '{mqtt_port}'",
        ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_PORT",
            status="PASS",
            message=f"MQTT broker port: {mqtt_port}",
            value_preview=mqtt_port,
        ))

    # 2. MQTT_TOPIC
    mqtt_topic = env_vars.get("MQTT_TOPIC", "").strip()
    if not mqtt_topic:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_TOPIC",
            status="FAIL",
            message="MQTT_TOPIC is missing or empty (e.g. hs109rs/# required).",
        ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_TOPIC",
            status="PASS",
            message=f"MQTT wildcard topic: {mqtt_topic}",
            value_preview=mqtt_topic,
        ))

    # 3. MQTT_USER & MQTT_PASS
    mqtt_user = env_vars.get("MQTT_USER", "").strip()
    if not mqtt_user:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_USER",
            status="FAIL",
            message="MQTT_USER is missing or empty.",
        ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_USER",
            status="PASS",
            message=f"MQTT authentication user: {mqtt_user}",
            value_preview=mqtt_user,
        ))

    mqtt_pass = env_vars.get("MQTT_PASS", "").strip()
    if not mqtt_pass:
        report.results.append(CheckResult(
            target=target,
            variable="MQTT_PASS",
            status="FAIL",
            message="MQTT_PASS is missing or empty.",
        ))
    else:
        banned_reason = check_is_banned(mqtt_pass)
        if banned_reason:
            report.results.append(CheckResult(
                target=target,
                variable="MQTT_PASS",
                status="FAIL",
                message=f"MQTT_PASS: {banned_reason}",
                value_preview=mask_secret(mqtt_pass),
            ))
        elif len(mqtt_pass) < 16 and mode == "prod":
            report.results.append(CheckResult(
                target=target,
                variable="MQTT_PASS",
                status="FAIL",
                message=f"MQTT_PASS is too short ({len(mqtt_pass)} chars). Minimum 16 characters required in production.",
                value_preview=mask_secret(mqtt_pass),
            ))
        else:
            report.results.append(CheckResult(
                target=target,
                variable="MQTT_PASS",
                status="PASS",
                message=f"MQTT password set with sufficient length ({len(mqtt_pass)} chars).",
                value_preview=mask_secret(mqtt_pass),
            ))

    # 4. HUB Identity (HUB_ID or HUB_NAME) & HUB_KEY
    hub_name = env_vars.get("HUB_NAME", env_vars.get("HUB_ID", "")).strip()
    if not hub_name:
        report.results.append(CheckResult(
            target=target,
            variable="HUB_NAME / HUB_ID",
            status="FAIL",
            message="HUB_NAME (or HUB_ID) is missing or empty.",
        ))
    else:
        report.results.append(CheckResult(
            target=target,
            variable="HUB_NAME",
            status="PASS",
            message=f"Hub Identity: {hub_name}",
            value_preview=hub_name,
        ))

    hub_key = env_vars.get("HUB_KEY", "").strip()
    if not hub_key:
        report.results.append(CheckResult(
            target=target,
            variable="HUB_KEY",
            status="FAIL",
            message="HUB_KEY is missing or empty. A 32-byte secret is required for HMAC payload signing.",
        ))
    else:
        banned_reason = check_is_banned(hub_key)
        if banned_reason:
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="FAIL",
                message=f"HUB_KEY: {banned_reason}",
                value_preview=mask_secret(hub_key),
            ))
        elif len(hub_key) < 32 and mode == "prod":
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="FAIL",
                message=f"HUB_KEY is too short ({len(hub_key)} chars). Minimum 32 hex/character entropy required.",
                value_preview=mask_secret(hub_key),
            ))
        else:
            report.results.append(CheckResult(
                target=target,
                variable="HUB_KEY",
                status="PASS",
                message="HUB_KEY meets entropy requirements (>= 32 chars).",
                value_preview=mask_secret(hub_key),
            ))

    # 5. SERVER API URL Endpoints
    url_keys = ["SERVER_URL", "SERVER_DEVICES_URL", "SERVER_ALERT_URL"]
    for key in url_keys:
        url_val = env_vars.get(key, "").strip()
        if not url_val:
            report.results.append(CheckResult(
                target=target,
                variable=key,
                status="FAIL",
                message=f"{key} is missing or empty.",
            ))
            continue

        try:
            parsed = urlparse(url_val)
            if mode == "prod" and parsed.scheme != "https":
                report.results.append(CheckResult(
                    target=target,
                    variable=key,
                    status="FAIL",
                    message=f"{key} must use HTTPS in production. Found: '{parsed.scheme}://'",
                    value_preview=url_val,
                ))
            elif mode == "prod" and not allow_localhost and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                report.results.append(CheckResult(
                    target=target,
                    variable=key,
                    status="FAIL",
                    message=f"{key} points to localhost in production mode.",
                    value_preview=url_val,
                ))
            else:
                report.results.append(CheckResult(
                    target=target,
                    variable=key,
                    status="PASS",
                    message=f"Valid endpoint URL: {url_val}",
                    value_preview=url_val,
                ))
        except Exception as e:
            report.results.append(CheckResult(
                target=target,
                variable=key,
                status="FAIL",
                message=f"Failed to parse {key}: {e}",
                value_preview=url_val,
            ))


# ==============================================================================
# CLI REPORT RENDERER
# ==============================================================================
def render_report(report: VerificationReport) -> None:
    # ANSI color codes
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    # Disable colors if not in tty
    if not sys.stdout.isatty():
        GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

    print(f"\n{CYAN}{BOLD}===================================================================={RESET}")
    print(f"{CYAN}{BOLD}    SMSB Platform Production Environment Verification (Task 10.2)   {RESET}")
    print(f"{CYAN}{BOLD}===================================================================={RESET}")
    print(f"Mode: {BOLD}{report.mode.upper()}{RESET}\n")

    current_target = None
    for res in report.results:
        if res.target != current_target:
            current_target = res.target
            print(f"{BOLD}[Target: {current_target}]{RESET}")

        if res.status == "PASS":
            badge = f"{GREEN}[PASS]{RESET}"
        elif res.status == "FAIL":
            badge = f"{RED}[FAIL]{RESET}"
        else:
            badge = f"{YELLOW}[WARN]{RESET}"

        var_name = f"{BOLD}{res.variable:<22}{RESET}"
        print(f"  {badge} {var_name} {res.message}")

    print(f"\n{CYAN}--------------------------------------------------------------------{RESET}")
    total = len(report.results)
    print(f"Summary: {total} checks | {GREEN}{report.pass_count} passed{RESET} | {YELLOW}{report.warn_count} warnings{RESET} | {RED}{report.failure_count} failed{RESET}")

    if report.has_failures:
        print(f"\n{RED}{BOLD}[!] REJECTION: Insecure or placeholder variables detected!{RESET}")
        print(f"{RED}Please update your .env files with strong cryptographically random values.{RESET}")
        print(f"{CYAN}Tip: Generate a 32-byte secret with:{RESET} {BOLD}openssl rand -hex 32{RESET}\n")
    else:
        print(f"\n{GREEN}{BOLD}[OK] All production environment checks PASSED! Safe to deploy.{RESET}\n")


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SMSB production environment configuration files.")
    parser.add_argument("--server-env", help="Path to server .env file", default=None)
    parser.add_argument("--hub-env", help="Path to hub .env file", default=None)
    parser.add_argument("--target", choices=["all", "server", "hub"], default="all", help="Target component to check")
    parser.add_argument("--mode", choices=["prod", "staging", "dev"], default="prod", help="Verification mode")
    parser.add_argument("--allow-localhost", action="store_true", help="Allow localhost in URLs (for local production testing)")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    server_env_path = Path(args.server_env) if args.server_env else repo_root / "server" / "v5" / ".env"
    hub_env_path = Path(args.hub_env) if args.hub_env else repo_root / "hub" / "V5" / ".env"

    report = VerificationReport(mode=args.mode)

    # Check Server env
    if args.target in {"all", "server"}:
        if server_env_path.exists():
            try:
                server_vars = parse_env_file(server_env_path)
                verify_server_env(server_vars, report, mode=args.mode, allow_localhost=args.allow_localhost)
            except Exception as e:
                report.results.append(CheckResult(
                    target="server",
                    variable=".env",
                    status="FAIL",
                    message=f"Failed to read/parse {server_env_path}: {e}",
                ))
        else:
            report.results.append(CheckResult(
                target="server",
                variable=".env",
                status="FAIL",
                message=f"Environment file not found at: {server_env_path}",
            ))

    # Check Hub env
    if args.target in {"all", "hub"}:
        if hub_env_path.exists():
            try:
                hub_vars = parse_env_file(hub_env_path)
                verify_hub_env(hub_vars, report, mode=args.mode, allow_localhost=args.allow_localhost)
            except Exception as e:
                report.results.append(CheckResult(
                    target="hub",
                    variable=".env",
                    status="FAIL",
                    message=f"Failed to read/parse {hub_env_path}: {e}",
                ))
        else:
            report.results.append(CheckResult(
                target="hub",
                variable=".env",
                status="FAIL",
                message=f"Environment file not found at: {hub_env_path}",
            ))

    render_report(report)
    return 1 if report.has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
