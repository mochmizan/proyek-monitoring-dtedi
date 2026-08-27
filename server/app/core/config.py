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
HUB_KEY: str = os.getenv("HUB_KEY", "rahasia_hub_01_xyz")
HUB_BOOTSTRAP_KEY: str = os.getenv("HUB_BOOTSTRAP_KEY", "")
ENV: str = os.getenv("ENV", "")

if os.getenv("HUB_KEY", "rahasia_hub_01_xyz") == "rahasia_hub_01_xyz" and os.getenv("ENV") == "prod":
    raise RuntimeError("HUB_KEY default 'rahasia_hub_01_xyz' is not allowed when ENV=prod — set a secure HUB_KEY")
if os.getenv("HUB_KEY") is None and os.getenv("ENV") != "prod":
    logging.warning("HUB_KEY not set — using default 'rahasia_hub_01_xyz' (only allowed when ENV!=prod)")

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
    "image/svg+xml": ".svg",
}
ALLOWED_FLOORPLAN_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_FLOORPLAN_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
