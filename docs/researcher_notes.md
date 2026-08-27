# Researcher Notes: IoT Hardening & RBAC

This document outlines the findings and implementation patterns for the User Authentication and Role-Based Access Control milestone, gathered using web research and the `ctx7` library query tools.

---

## 1. Argon2id Password Hashing & Timing-Safe Verification

### Package Installation
The `argon2-cffi` package (version `>=23.1.0`) provides timing-safe Argon2id password hashing for Python. It is configured as follows:
```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()
```

### Timing-Safe Non-Existent User Verification
To prevent username enumeration via timing attacks (since Argon2 hashing is intentionally CPU-intensive), we must compute a static dummy hash at server startup and perform verification against it when the username is not found:
```python
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

ph = PasswordHasher()

# Generate a cryptographically secure dummy hash at startup
# using the active PasswordHasher settings.
DUMMY_PASSWORD = secrets.token_urlsafe(32)
DUMMY_HASH = ph.hash(DUMMY_PASSWORD)

def verify_password_safe(stored_hash: str | None, password: str) -> bool:
    """
    Verify password against stored_hash. If stored_hash is None (user missing),
    verify against a dummy hash to prevent timing attacks.
    """
    if stored_hash is None:
        # Run dummy verification to mimic the timing of a real hashing run
        try:
            ph.verify(DUMMY_HASH, password)
        except VerifyMismatchError:
            pass  # Expected to mismatch
        except VerificationError:
            pass
        return False

    try:
        return ph.verify(stored_hash, password)
    except VerifyMismatchError:
        return False
    except VerificationError:
        return False
```

---

## 2. Sliding Session Expiry with an Absolute Cap

The session model tracks session metadata. To enforce sliding window validity with a hard boundary (maximum exposure mitigation), the verification logic performs a check against the creation timestamp `created_at` and updates `expires_at`:

### Session Verification Logic
```python
import datetime
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import Session

# SQLAlchemy Session Model
class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(String, primary_key=True, index=True) # Secure token (e.g. UUID)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

# Custom Exceptions for Cookie Clearing
class SessionExpired(Exception):
    pass

# Exception Handler to clear cookie
app = FastAPI()

@app.exception_handler(SessionExpired)
async def session_expired_handler(request: Request, exc: SessionExpired):
    response = JSONResponse(
        status_code=401,
        content={"detail": "Session expired or invalid. Please login again."}
    )
    response.delete_cookie("session_id", path="/")
    return response

# FastAPI Dependency
def get_current_user_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise SessionExpired()
        
    db_session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not db_session:
        raise SessionExpired()
        
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 1. Absolute Cap Check (12-hour limit)
    absolute_expiry = db_session.created_at + datetime.timedelta(hours=12)
    if now > absolute_expiry:
        db.delete(db_session)
        db.commit()
        raise SessionExpired()
        
    # 2. Sliding Window Check (e.g., 2 hours sliding window)
    if now > db_session.expires_at:
        db.delete(db_session)
        db.commit()
        raise SessionExpired()
        
    # 3. Slide the Expiration (capped at the 12-hour limit)
    sliding_window = datetime.timedelta(hours=2)
    db_session.expires_at = min(now + sliding_window, absolute_expiry)
    db.commit()
    
    return db_session
```

---

## 3. Login Lockout Rate Limiting per Username

To prevent brute force attacks, a lockout mechanism tracks consecutive failures on a per-username basis.
- Lockout occurs after **5 consecutive failed attempts**.
- The lockout duration is **15 minutes**.
- Response code is explicitly `423 Locked`.
- Track attempts for every username string to prevent user enumeration timing attacks.

### Database (SQLAlchemy) Implementation
```python
class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    
    username = Column(String, primary_key=True, index=True) # Normalized
    attempts = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)

def handle_db_lockout(username: str, db: Session, success: bool):
    normalized = username.strip().lower()
    now = datetime.datetime.now(datetime.timezone.utc)
    
    attempt = db.query(LoginAttempt).filter(LoginAttempt.username == normalized).first()
    
    if attempt:
        if attempt.locked_until and attempt.locked_until > now:
            raise HTTPException(
                status_code=423,
                detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes."
            )
        
        # Reset expired lock
        if attempt.locked_until and attempt.locked_until <= now:
            attempt.attempts = 0
            attempt.locked_until = None
            db.commit()

    if success:
        if attempt:
            db.delete(attempt)
            db.commit()
        return
        
    if not attempt:
        attempt = LoginAttempt(username=normalized, attempts=1, last_attempt_at=now)
        db.add(attempt)
    else:
        attempt.attempts += 1
        attempt.last_attempt_at = now
        if attempt.attempts >= 5:
            attempt.locked_until = now + datetime.timedelta(minutes=15)
            
    db.commit()
    
    if attempt.attempts >= 5:
        raise HTTPException(
            status_code=423,
            detail="Account is temporarily locked due to too many failed attempts. Try again in 15 minutes."
        )
```

---

## 4. Multiple Roles Verification

FastAPI dependency checking must support multiple roles:
```python
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from databasev5 import get_db

def require_role(*allowed_roles: str):
    def dependency(request: Request, db: Session = Depends(get_db)):
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
            
        # Verify session and get user
        user = get_user_from_session(db, session_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session invalid or expired"
            )
            
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
            
        return user
    return dependency
```

---

## 5. Command Action-Level Role Splitting

To enforce distinct security requirements for device actions:
- `mode` or `start_genset` commands -> allowed for `admin` or `operator`
- `reset` commands -> allowed only for `admin`

### Endpoint Validation
```python
@api.post("/api/devices/{dev_id}/command")
def send_device_command(
    request: Request,
    dev_id: str,
    body: dict,
    db: Session = Depends(get_db)
):
    # Retrieve user from session
    session_id = request.cookies.get("session_id")
    user = get_user_from_session(db, session_id)
    if not user:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
         
    # Check roles based on action
    is_reset = body.get("reset") is not None
    
    if is_reset:
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reset action requires admin role")
    else:
        if user.role not in ["admin", "operator"]:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Action requires admin or operator role")
             
    # Continue validation and execution...
```
