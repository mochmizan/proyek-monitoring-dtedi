# app/main.py — FastAPI assembly (split from hubgatev5.py)
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from auth import SessionExpired, session_expired_handler
from app.core.config import CORS_ALLOWED_ORIGINS, STATIC_DIR, FLOORPLAN_UPLOAD_DIR
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.routers import auth as auth_router
from app.routers import hubs as hubs_router
from app.routers import rooms as rooms_router
from app.routers import devices as devices_router
from app.routers import alerts as alerts_router
from app.routers import iot as iot_router
from app.routers import commands as commands_router
from app.routers import schedules as schedules_router
from app.services.scheduler import scheduler_lifespan

# Ensure logging configured
configure_logging()

# Ensure static dirs exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(FLOORPLAN_UPLOAD_DIR, exist_ok=True)

# Import fail-fast checks from config (already executed on import)
import app.core.config  # noqa: F401

api = FastAPI(title="HubGate V5 - Secure API Gateway", lifespan=scheduler_lifespan)
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api.add_exception_handler(SessionExpired, session_expired_handler)

# CORS
cors_origins_str = CORS_ALLOWED_ORIGINS.strip()
if cors_origins_str:
    origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
    allow_credentials = True
    if "*" in origins:
        allow_credentials = False
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Health check — no auth, no rate limit
@api.get("/health")
@api.get("/api/health")
def health_check():
    db_status = "up"
    try:
        from databasev5 import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "up"
        finally:
            db.close()
    except Exception:
        db_status = "down"
    return {"status": "ok", "db": db_status}


# Mount static
api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include routers (order does not matter but keep logical grouping)
api.include_router(auth_router.router)
api.include_router(hubs_router.router)
api.include_router(rooms_router.router)
api.include_router(devices_router.router)
api.include_router(alerts_router.router)
api.include_router(iot_router.router)
api.include_router(commands_router.router)
api.include_router(schedules_router.router)
