# app/routers/auth.py
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import User
from auth import get_current_user, create_session, delete_session, handle_db_lockout, verify_password_safe
from schemas_auth import UserLoginPayload, UserResponse
from app.core.rate_limit import limiter

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login", response_model=UserResponse)
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
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes.",
                )

    user = db.query(User).filter(User.username == normalized_username).first()
    password_matched = verify_password_safe(user.password_hash if user else None, payload.password)

    if not user or not password_matched:
        handle_db_lockout(payload.username, db, success=False)
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    handle_db_lockout(payload.username, db, success=True)
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

    return UserResponse(
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(db, session_id)
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.delete_cookie("session_id", httponly=True, secure=is_secure, samesite="lax", path="/")
    return {"status": "logged_out"}


@router.get("/api/auth/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return UserResponse(
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
    )
