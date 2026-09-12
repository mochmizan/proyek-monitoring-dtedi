import json
import logging
import logging.config
import os
import time
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

access_logger = logging.getLogger("smsb.access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Structured JSON request logging middleware.
    Outputs single-line JSON with timestamp, request_id, method, path, status_code, latency_ms, client_ip.
    Attaches X-Request-ID to response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            try:
                from app.core.rate_limit import get_forwarded_address
                client_ip = get_forwarded_address(request)
            except Exception:
                client_ip = request.client.host if request.client and hasattr(request.client, "host") else "127.0.0.1"

            log_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "client_ip": client_ip,
            }
            access_logger.info(json.dumps(log_record))


def configure_logging():
    # Use JSON formatter if python-json-logger is available and requested
    log_format = os.getenv("LOG_FORMAT", "standard").lower()
    use_json = False
    if log_format == "json":
        try:
            import pythonjsonlogger  # noqa: F401
            use_json = True
        except ImportError:
            use_json = False

    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        },
        "handlers": {
            "default": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
        },
        "root": {"level": "INFO", "handlers": ["default"]},
    }
    if use_json:
        cfg["formatters"]["json"] = {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "timestamp": "asctime",
        }
        cfg["handlers"]["default"]["formatter"] = "json"

    try:
        logging.config.dictConfig(cfg)
    except Exception:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Dedicated access logger for structured JSON request logs
    # Formatter is plain %(message)s so that json.dumps output is emitted as clean single-line JSON
    if not any(isinstance(h, logging.StreamHandler) for h in access_logger.handlers):
        access_handler = logging.StreamHandler()
        access_handler.setFormatter(logging.Formatter("%(message)s"))
        access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.disabled = False
    access_logger.propagate = False
