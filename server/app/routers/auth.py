# app/routers/auth.py
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import User, UserSession, UserAuditLog
from auth import (
    get_current_user,
    create_session,
    delete_session,
    handle_db_lockout,
    verify_password_safe,
    hash_password,
)
from schemas_auth import UserLoginPayload, UserResponse, ChangePasswordRequest
from app.core.rate_limit import limiter
from app.core.csrf import create_csrf_token, require_csrf, validate_login_request

router = APIRouter(tags=["auth"])


@router.post(
    "/api/auth/login",
    response_model=UserResponse,
    dependencies=[Depends(validate_login_request)],
)
@limiter.limit("5/minute")
def login(
    request: Request,
    payload: UserLoginPayload,
    response: Response,
    db: Session = Depends(get_db),
):
    normalized_username = payload.username.strip().lower()
    now = datetime.now(UTC)

    attempt = db.query(__import__("modelsv5", fromlist=["LoginAttempt"]).LoginAttempt).filter(
        __import__("modelsv5", fromlist=["LoginAttempt"]).LoginAttempt.username == normalized_username
    ).first()
    if attempt:
        locked_until = attempt.locked_until
        if locked_until:
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if locked_until > now:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes.",
                )

    user = db.query(User).filter(User.username == normalized_username).first()
    password_matched = verify_password_safe(user.password_hash if user else None, payload.password)

    if not user or not password_matched:
        handle_db_lockout(payload.username, db, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Tambahan: Proteksi jika akun dinonaktifkan
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    handle_db_lockout(payload.username, db, success=True)

    # Tambahan: Catat waktu login terakhir
    user.last_login_at = now
    db.commit()

    session = create_session(db, user.id)

    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
        max_age=7200,
    )

    return UserResponse.model_validate(user)


@router.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_csrf),
):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(db, session_id)
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.delete_cookie("session_id", httponly=True, secure=is_secure, samesite="lax", path="/")
    return {"status": "logged_out"}


@router.get("/api/auth/csrf-token")
def get_csrf_token(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    session_id = request.cookies.get("session_id")

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session tidak ditemukan, silakan login kembali",
        )

    token = create_csrf_token(session_id)

    # Mencegah browser/proxy menyimpan cache response token ini
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return {"csrf_token": token}


@router.get("/api/auth/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return UserResponse.model_validate(current_user)


# Tambahan: Endpoint Ganti Password Mandiri
@router.post("/api/auth/change-password", status_code=status.HTTP_200_OK)
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_csrf)
):
    # 1. Verifikasi password lama
    if not verify_password_safe(current_user.password_hash, req.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password lama Anda salah"
        )

    # 2. Cek password baru tidak boleh sama dengan password lama
    if req.old_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password baru tidak boleh sama dengan password lama"
        )

    now = datetime.now(UTC)

    # 3. Hash password baru & update user
    current_user.password_hash = hash_password(req.new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = now
    current_user.updated_at = now

    # 4. Revoke seluruh sesi (termasuk sesi saat ini) agar user wajib login ulang[cite: 1]
    db.query(UserSession).filter(UserSession.user_id == current_user.id).delete()

    # 5. Hapus cookie session dari browser[cite: 1]
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.delete_cookie("session_id", httponly=True, secure=is_secure, samesite="lax", path="/")

    # 6. Catat ke Audit Log[cite: 1]
    ip_addr = request.client.host if request.client else None
    audit = UserAuditLog(
        actor_id=current_user.id,
        action="CHANGE_PASSWORD",
        target_user_id=current_user.id,
        status="SUCCESS",
        ip_address=ip_addr,
        details="User changed password successfully"
    )
    db.add(audit)

    db.commit()

    return {
        "status": "success",
        "message": "Password berhasil diubah. Silakan login kembali dengan password baru Anda."
    }
