# app/__init__.py — re-exports for sibling imports compat
try:
    from app.main import api  # noqa: F401
except Exception:
    # During import-time fail-fast, api may not be importable; ignore
    pass

# Also re-export helpers that tests import from hubgatev5 directly
try:
    from app.core.rate_limit import get_forwarded_address  # noqa: F401
    from app.routers.rooms import resolve_static_disk_path, FLOORPLAN_UPLOAD_DIR  # noqa: F401
    from app.services.alert_engine import evaluate_device_thresholds  # noqa: F401
except Exception:
    pass
