import os
import secrets
import uuid
import datetime
from datetime import UTC, timedelta
from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from databasev5 import get_db
from modelsv5 import User, UserSession, LoginAttempt

# 1. Inisialisasi Password Hasher Argon2id
ph = PasswordHasher()

# Generate cryptographically secure dummy hash di startup untuk timing-safe verification
DUMMY_PASSWORD = secrets.token_urlsafe(32)
DUMMY_HASH = ph.hash(DUMMY_PASSWORD)

def verify_password_safe(stored_hash: str | None, password: str) -> bool:
    """
    Memverifikasi password terhadap stored_hash. Jika stored_hash adalah None (user tidak ditemukan),
    maka akan dilakukan verifikasi terhadap dummy hash untuk mencegah username enumeration timing attack.
    """
    if stored_hash is None:
        try:
            ph.verify(DUMMY_HASH, password)
        except VerifyMismatchError:
            pass
        except VerificationError:
            pass
        return False

    try:
        return ph.verify(stored_hash, password)
    except Exception:
        return False

def hash_password(password: str) -> str:
    """
    Meng-hash password menggunakan settings default argon2 PasswordHasher.
    """
    return ph.hash(password)


# 2. Custom Exception untuk Session Kedaluwarsa
class SessionExpired(Exception):
    pass


# Exception Handler untuk membersihkan cookie "session_id" dan mengembalikan status 401
async def session_expired_handler(request: Request, exc: SessionExpired):
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Session expired or invalid. Please login again."}
    )
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.delete_cookie("session_id", path="/", httponly=True, secure=is_secure, samesite="lax")
    origin = request.headers.get("origin")
    if origin:
        cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
        allowed = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
        if origin in allowed or "*" in allowed:
            response.headers["access-control-allow-origin"] = origin
            response.headers["access-control-allow-credentials"] = "true"
    return response


# 3. Session Management Functions
def create_session(db: Session, user_id: str) -> UserSession:
    """
    Membuat session baru yang berlaku selama 2 jam sejak pembuatan.
    """
    session_id = str(uuid.uuid4())
    now = datetime.datetime.now(UTC)
    expires_at = now + timedelta(hours=2)

    db_session = UserSession(
        session_id=session_id,
        user_id=user_id,
        expires_at=expires_at,
        created_at=now
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


def verify_session(db: Session, session_id: str) -> User | None:
    """
    Memverifikasi kevalidan session berdasarkan sliding window 2 jam dan limit absolut 12 jam.
    """
    db_session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if not db_session:
        raise SessionExpired()

    now = datetime.datetime.now(UTC)

    # Pastikan database datetime aware jika kembali sebagai naive (misal di SQLite)
    created_at = db_session.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    expires_at = db_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    # A. Cek Limit Absolut (12 Jam)
    absolute_expiry = created_at + timedelta(hours=12)
    if now > absolute_expiry:
        db.delete(db_session)
        db.commit()
        raise SessionExpired()

    # B. Cek Sliding Window Idle (2 Jam)
    if now > expires_at:
        db.delete(db_session)
        db.commit()
        raise SessionExpired()

    # C. Perbarui Waktu Kedaluwarsa (sliding capped pada 12 jam absolut) dengan throttling
    # SEC-10: Hanya eksekusi UPDATE jika sisa validitas < 90 menit.
    # Request dengan session segar (remaining >= 90 menit) melompati write DB sepenuhnya.
    remaining_validity = expires_at - now
    if remaining_validity < timedelta(minutes=90):
        sliding_window = timedelta(hours=2)
        db_session.expires_at = min(now + sliding_window, absolute_expiry)
        db.commit()

    # Ambil data user
    user = db.query(User).filter(User.id == db_session.user_id).first()
    return user


def delete_session(db: Session, session_id: str):
    """
    Menghapus session dari database (logout).
    """
    db_session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if db_session:
        db.delete(db_session)
        db.commit()


# 4. Dependency untuk Mendapatkan User yang Sedang Login
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    FastAPI Dependency untuk mengambil user berdasarkan session_id cookie.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise SessionExpired()

    user = verify_session(db, session_id)
    if not user:
        raise SessionExpired()

    return user


# 5. Dependency Factory untuk Validasi Peran (RBAC)
def require_role(*allowed_roles: str):
    """
    FastAPI Dependency Factory untuk membatasi akses endpoint hanya untuk role tertentu.
    """
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return current_user
    return dependency


# 6. Lockout Rate Limiting (Database-Backed)
def handle_db_lockout(username: str, db: Session, success: bool):
    """
    Mengelola lockout akun berbasis username untuk mencegah brute force attack.
    Jika login gagal berturut-turut sebanyak 5 kali, akun di-lockout selama 15 menit.
    """
    normalized = username.strip().lower()
    now = datetime.datetime.now(UTC)

    attempt = db.query(LoginAttempt).filter(LoginAttempt.username == normalized).first()

    # A. Periksa status lockout saat ini
    if attempt:
        locked_until = attempt.locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)

        if locked_until and locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes."
            )

        # Reset kunci jika masa lockout sudah terlewati
        if locked_until and locked_until <= now:
            attempt.attempts = 0
            attempt.locked_until = None
            db.commit()

    # B. Jika login sukses, hapus rekam jejak kegagalan
    if success:
        if attempt:
            db.delete(attempt)
            db.commit()
        return

    # C. Jika login gagal, perbarui jumlah kegagalan
    if not attempt:
        attempt = LoginAttempt(username=normalized, attempts=1, last_attempt_at=now)
        db.add(attempt)
    else:
        attempt.attempts += 1
        attempt.last_attempt_at = now
        if attempt.attempts >= 5:
            attempt.locked_until = now + timedelta(minutes=15)

    db.commit()

    # D. Berikan respon lockout jika batas kegagalan tercapai
    if attempt.attempts >= 5:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes."
        )
