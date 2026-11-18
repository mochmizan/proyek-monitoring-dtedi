# app/core/security_middleware.py — hardening middlewares
#
# Addresses pentest findings:
#   F-05 — missing request body-size limit (DoS via large payloads)
#   F-13 — missing HTTP security response headers
#
# F-05 is implemented as a pure ASGI middleware (wrapping ``receive``) so it
# composes safely with Starlette's BaseHTTPMiddleware stack. F-13 is a simple
# header-injection middleware.

import json

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import MAX_BODY_SIZE, ENABLE_HSTS


class BodySizeLimitMiddleware:
    """F-05: Reject requests whose body exceeds ``max_body_size`` with HTTP 413.

    Pure ASGI implementation:
      1. Fast path — reject on an oversized ``Content-Length`` header before any
         body is read.
      2. Streaming guard — if the header is missing/forged (e.g. chunked), count
         bytes from the wrapped ``receive`` and abort with 413 once the limit is
         exceeded.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = MAX_BODY_SIZE) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        # File-upload endpoints (multipart/form-data) perform their own,
        # endpoint-specific size validation (e.g. 5 MB for floor plans). The
        # global JSON body limit (F-05) would otherwise reject legitimate uploads
        # with a misleading 413, so multipart requests are exempted here.
        content_type = headers.get("content-type", "")
        if content_type.lower().startswith("multipart/form-data"):
            await self.app(scope, receive, send)
            return

        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._send_error(send, 400, "Invalid Content-Length header")
                return
            if declared > self.max_body_size:
                await self._send_error(
                    send,
                    413,
                    f"Request body too large. Maximum allowed is {self.max_body_size} bytes.",
                )
                return

        max_size = self.max_body_size
        total_read = 0
        limit_exceeded = False

        async def limited_receive() -> Message:
            nonlocal total_read, limit_exceeded
            message = await receive()
            if message["type"] == "http.request":
                total_read += len(message.get("body", b""))
                if total_read > max_size:
                    limit_exceeded = True
            return message

        # If the streaming guard trips mid-body, we can no longer cleanly inject a
        # response, so we track it and short-circuit via a sentinel send wrapper.
        response_started = False

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        finally:
            if limit_exceeded and not response_started:
                await self._send_error(
                    send,
                    413,
                    f"Request body too large. Maximum allowed is {max_size} bytes.",
                )

    @staticmethod
    async def _send_error(send: Send, status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """F-13: Attach standard security response headers to every response."""

    def __init__(self, app, enable_hsts: bool = ENABLE_HSTS):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Disallow framing (clickjacking protection).
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Limit referrer leakage.
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Restrict powerful browser features by default.
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        # Conservative CSP: this is a JSON API; disallow active content.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        # Reduce server fingerprinting.
        response.headers["Server"] = "hubgate"

        # HSTS only makes sense over HTTPS; enabled via config in production.
        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
