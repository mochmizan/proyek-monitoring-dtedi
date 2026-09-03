# app/core/rate_limit.py — limiter with trusted proxy forwarded IP resolution
from fastapi import Request
from slowapi import Limiter
from app.core.config import ForwardedAllowIPS

# Parse trusted proxies from comma-separated string / loopback defaults
TRUSTED_PROXIES = {ip.strip() for ip in ForwardedAllowIPS.split(",") if ip.strip()} | {
    "127.0.0.1",
    "::1",
    "testclient",  # Support FastAPI TestClient in test environments
}


def get_forwarded_address(request: Request) -> str:
    """
    Resolve client IP address. Only trusts X-Forwarded-For or X-Real-IP if the
    immediate client connection originates from a trusted reverse proxy (SEC-01).
    """
    client_host = request.client.host if request.client and hasattr(request.client, "host") else "127.0.0.1"
    if client_host in TRUSTED_PROXIES:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and real_ip.strip():
            return real_ip.strip()
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for and forwarded_for.strip():
            parts = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
            if parts:
                return parts[0]
    return client_host


limiter = Limiter(key_func=get_forwarded_address)
