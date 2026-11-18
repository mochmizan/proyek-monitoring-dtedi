# app/core/config.py — centralized env & fail-fast checks
import os
import logging

from dotenv import load_dotenv

load_dotenv()

# --- ForwardedAllowIPS / trusted proxy ---
# NOTE: Trusted proxy is 127.0.0.1 (Nginx) — only trust X-Forwarded-For / X-Real-IP
# when request comes via trusted proxy. ForwardedAllowIPS env can be used to
# configure additional trusted proxy CIDRs (document-only; code trusts loopback).
ForwardedAllowIPS = os.getenv("ForwardedAllowIPS", "127.0.0.1")

# --- Database ---
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./hubgatev5.db")
DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

# Fail-fast: DATABASE_URL must be explicitly set when ENV=prod
if not os.getenv("DATABASE_URL") and os.getenv("ENV") == "prod":
    raise RuntimeError("DATABASE_URL must be set when ENV=prod — refusing to start with SQLite fallback")

# --- Hub keys ---
# NOTE: the default below is an obvious, non-secret placeholder used only for
# local development. The real HUB_KEY MUST come from the environment/.env in
# production; the fail-fast guard rejects the placeholder when ENV=prod.
_HUB_KEY_DEV_DEFAULT = "dev-insecure-change-me"
HUB_KEY: str = os.getenv("HUB_KEY", _HUB_KEY_DEV_DEFAULT)
HUB_BOOTSTRAP_KEY: str = os.getenv("HUB_BOOTSTRAP_KEY", "")
ENV: str = os.getenv("ENV", "")

if os.getenv("HUB_KEY", _HUB_KEY_DEV_DEFAULT) == _HUB_KEY_DEV_DEFAULT and os.getenv("ENV") == "prod":
    raise RuntimeError(
        f"HUB_KEY default '{_HUB_KEY_DEV_DEFAULT}' is not allowed when ENV=prod — set a secure HUB_KEY"
    )
if os.getenv("HUB_KEY") is None and os.getenv("ENV") != "prod":
    logging.warning(
        "HUB_KEY not set — using insecure dev default (only allowed when ENV!=prod)"
    )

# --- CORS ---
CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://example.com")

# --- Static ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC_DIR: str = os.getenv("STATIC_DIR", os.path.join(BASE_DIR, "static"))
FLOORPLAN_UPLOAD_DIR: str = os.getenv("FLOORPLAN_UPLOAD_DIR", os.path.join(STATIC_DIR, "uploads", "floorplans"))

# --- Floorplan validation constants ---
ALLOWED_FLOORPLAN_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
ALLOWED_FLOORPLAN_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_FLOORPLAN_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# --- CSRF ---
CSRF_SECRET = os.getenv("CSRF_SECRET", "").strip()

if len(CSRF_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("CSRF_SECRET must contain at least 32 bytes")


# ---------------------------------------------------------------------------
# Security hardening settings (pentest findings F-05, F-06, F-13, F-14, F-16)
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logging.warning("Invalid integer for %s=%r — falling back to default %d", name, raw, default)
        return default


# Is the service running in production? Used to toggle docs exposure (F-14),
# HSTS strictness (F-13), and secure-cookie defaults (F-16).
IS_PROD: bool = ENV == "prod"

# --- F-05: maximum accepted request body size (bytes). Default 1 MB. ---
MAX_BODY_SIZE: int = _env_int("MAX_BODY_SIZE", 1 * 1024 * 1024)

# --- F-06: reject telemetry whose event timestamp is further in the future
# than this many seconds relative to server "now". Default 86400s (24 hours):
# generous enough for clock skew / legitimate near-future writes, while still
# rejecting absurd future-dated injection that would corrupt history/alerts. ---
MAX_FUTURE_TIMESTAMP_SECONDS: int = _env_int("MAX_FUTURE_TIMESTAMP_SECONDS", 24 * 3600)
# Retain historical backfill window (how far in the past is still accepted).
MAX_PAST_TIMESTAMP_SECONDS: int = _env_int("MAX_PAST_TIMESTAMP_SECONDS", 35 * 24 * 3600)

# --- F-14: expose interactive API docs only when NOT in production, unless
# explicitly overridden with ENABLE_DOCS=true. ---
ENABLE_DOCS: bool = _env_bool("ENABLE_DOCS", not IS_PROD)

# --- F-16: the Secure flag on the session cookie must be decided by server
# configuration, never by a client-supplied header. Defaults to True in prod. ---
COOKIE_SECURE: bool = _env_bool("COOKIE_SECURE", IS_PROD)

# --- F-13: enable HTTP Strict-Transport-Security. Defaults to on in prod. ---
ENABLE_HSTS: bool = _env_bool("ENABLE_HSTS", IS_PROD)

# --- F-04: per-hub ingest rate limits (requests/minute). ---
IOT_RATE_LIMIT_PER_HUB: str = os.getenv("IOT_RATE_LIMIT_PER_HUB", "1200/minute")
IOT_BATCH_RATE_LIMIT_PER_HUB: str = os.getenv("IOT_BATCH_RATE_LIMIT_PER_HUB", "60/minute")
