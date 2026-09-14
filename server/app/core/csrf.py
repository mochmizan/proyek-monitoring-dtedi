import hashlib
import hmac
from fastapi import Depends, HTTPException, Request, status
from modelsv5 import User
from auth import get_current_user
from app.core.config import CORS_ALLOWED_ORIGINS, CSRF_SECRET

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _csrf_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message},
    )


def create_csrf_token(session_id: str) -> str:
    """Membuat CSRF token yang terikat unik dengan ID sesi login."""
    return hmac.new(
        CSRF_SECRET.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

def validate_csrf_request(request: Request) -> None:
    """Validasi CSRF token pada HTTP Method yang mengubah data (POST, PUT, PATCH, DELETE)."""
    # Method aman tidak perlu validasi.
    if request.method.upper() in SAFE_METHODS:
        return

    # Login creates a fresh session and cannot present a token for that session yet.
    if request.url.path == "/api/auth/login":
        return

    session_id = request.cookies.get("session_id")

    # Tanpa cookie, dependency autentikasi endpoint tetap menentukan hasil request.
    if not session_id:
        return

    received_token = request.headers.get("X-CSRF-Token")

    if not received_token:
        raise _csrf_error(
            "CSRF_TOKEN_MISSING",
            "CSRF token wajib disertakan di header X-CSRF-Token",
        )

    expected_token = create_csrf_token(session_id)

    # Fast-comparison aman dari serangan timing attack
    if not hmac.compare_digest(received_token, expected_token):
        raise _csrf_error(
            "CSRF_TOKEN_INVALID",
            "CSRF token tidak valid",
        )


def validate_login_request(request: Request) -> None:
    """Restrict browser login requests without requiring a session CSRF token."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "LOGIN_CONTENT_TYPE_INVALID",
                "message": "Login requires Content-Type: application/json",
            },
        )

    origin = request.headers.get("origin")
    if not origin:
        return

    allowed_origins = {
        item.strip().rstrip("/")
        for item in CORS_ALLOWED_ORIGINS.split(",")
        if item.strip() and item.strip() != "*"
    }
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    scheme = forwarded_proto or request.url.scheme
    host = request.headers.get("host", "")
    same_origin = f"{scheme}://{host}" if host else ""

    if origin.rstrip("/") not in allowed_origins and origin.rstrip("/") != same_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "LOGIN_ORIGIN_INVALID",
                "message": "Login origin is not allowed",
            },
        )


def require_csrf(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency untuk endpoint user biasa yang mengubah data."""
    validate_csrf_request(request)
    return current_user

