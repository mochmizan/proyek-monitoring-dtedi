import hashlib
import hmac
import os
from urllib.parse import urlsplit

import httpx
import pytest


os.environ.setdefault("CSRF_SECRET", "test-only-csrf-secret-32-bytes-minimum")


@pytest.fixture(autouse=True)
def browser_clients_send_csrf(monkeypatch):
    """Make legacy TestClient calls behave like the dashboard's API wrapper."""
    original_request = httpx.Client.request

    def request_with_csrf(self, method, url, **kwargs):
        request_headers = httpx.Headers(kwargs.get("headers"))
        path = urlsplit(str(url)).path
        unsafe = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}

        request_cookies = kwargs.get("cookies")
        session_id = request_cookies.get("session_id") if request_cookies else None
        if not session_id:
            try:
                session_id = self.cookies.get("session_id")
            except httpx.CookieConflict:
                session_id = None

        if unsafe and path != "/api/auth/login" and session_id and "X-CSRF-Token" not in request_headers:
            request_headers["X-CSRF-Token"] = hmac.new(
                os.environ["CSRF_SECRET"].encode("utf-8"),
                session_id.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            kwargs["headers"] = request_headers

        return original_request(self, method, url, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", request_with_csrf)
