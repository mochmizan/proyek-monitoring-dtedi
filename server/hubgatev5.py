# hubgatev5.py — shim for compat (split into app/ structure)
# Preserves uvicorn hubgatev5:api and `from hubgatev5 import api` for tests.
from app.main import api  # noqa: F401

# Re-export helpers for tests that import them from hubgatev5
try:
    from app.routers.rooms import resolve_static_disk_path, remove_floor_plan_file  # noqa: F401
    from app.core.config import FLOORPLAN_UPLOAD_DIR, STATIC_DIR  # noqa: F401
    from app.core.rate_limit import get_forwarded_address  # noqa: F401
    from app.services.alert_engine import evaluate_device_thresholds  # noqa: F401
    from app.services.presence import HUB_ONLINE_WINDOW_SECONDS  # noqa: F401
    from app.routers.alerts import parse_datetime_param  # noqa: F401
except Exception:
    pass

# Also expose limiter / ForwardedAllowIPS docs for completeness
try:
    from app.core.rate_limit import limiter  # noqa: F401
except Exception:
    pass
