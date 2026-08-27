# app/core/logging.py — JSON structured logging via dictConfig
import logging
import logging.config
import json
import os

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "standard": {
            "format": "%(asctime)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["default"],
    },
}

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
            "standard": {"format": "%(asctime)s %(levelname)s %(message)s"},
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
        }
        cfg["handlers"]["default"]["formatter"] = "json"

    try:
        logging.config.dictConfig(cfg)
    except Exception:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
