# app/core/rate_limit.py — limiter with forwarded IP fix (parts[0])
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_forwarded_address(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for and forwarded_for.strip():
        parts = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        if parts:
            # Use left-most (original client) IP; parts[-1] would be last proxy — wrong behind trusted proxy 127.0.0.1
            return parts[0]
    return get_remote_address(request)


limiter = Limiter(key_func=get_forwarded_address)
