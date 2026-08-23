# test_auth_milestone3a.py
# Unit/Integration Tests for Phase 3A (DB & Core Auth)

import os
import sys
import uuid
import datetime
from datetime import UTC, timedelta
import pytest
from unittest.mock import MagicMock

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_auth_milestone3a.db"

# Clean old database if exists
if os.path.exists("./test_auth_milestone3a.db"):
    try:
        os.remove("./test_auth_milestone3a.db")
    except Exception:
        pass

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import User, UserSession, LoginAttempt
from auth import (
    ph,
    verify_password_safe,
    hash_password,
    SessionExpired,
    create_session,
    verify_session,
    delete_session,
    get_current_user,
    require_role,
    handle_db_lockout
)
from schemas_auth import UserLoginPayload, UserResponse
from create_admin_user import create_or_update_user
from fastapi import HTTPException

def test_password_hashing():
    print("--- Test: Password Hashing & Timing-Safe Verification ---")
    password = "supersecurepassword"
    h = hash_password(password)
    assert h != password
    assert ph.verify(h, password) is True
    
    # Test verify_password_safe
    assert verify_password_safe(h, password) is True
    assert verify_password_safe(h, "wrongpassword") is False
    # Test dummy verification when stored_hash is None (should return False)
    assert verify_password_safe(None, password) is False

def test_create_admin_user_cli_and_db():
    print("--- Test: CLI create_or_update_user and User model ---")
    username = "admin_test"
    password = "admin_password"
    display_name = "Test Admin User"
    role = "admin"
    
    # Run creation
    create_or_update_user(username, password, display_name, role)
    
    db = SessionLocal()
    try:
        # Check user in database
        user = db.query(User).filter(User.username == username).first()
        assert user is not None
        assert user.display_name == display_name
        assert user.role == role
        assert verify_password_safe(user.password_hash, password) is True
        
        # Test update user
        new_display_name = "Updated Admin User"
        create_or_update_user(username, "new_password", new_display_name, "operator")
        
        # Refresh from DB
        db.expire_all()
        user = db.query(User).filter(User.username == username).first()
        assert user.display_name == new_display_name
        assert user.role == "operator"
        assert verify_password_safe(user.password_hash, "new_password") is True
        assert verify_password_safe(user.password_hash, password) is False
    finally:
        db.close()

def test_session_management():
    print("--- Test: Session Management (Creation, Verification, Sliding, Expiry) ---")
    db = SessionLocal()
    try:
        # Create test user
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username="session_test_user",
            password_hash=hash_password("password"),
            display_name="Session User",
            role="operator"
        )
        db.add(user)
        db.commit()
        
        # 1. Create session
        sess = create_session(db, user_id)
        session_id = sess.session_id
        assert session_id is not None
        assert sess.user_id == user_id
        
        # 2. Verify session immediately (should succeed and slide expires_at)
        initial_expires = sess.expires_at
        verified_user = verify_session(db, session_id)
        assert verified_user.id == user_id
        # expires_at should be updated (slightly after now)
        db.refresh(sess)
        assert sess.expires_at >= initial_expires
        
        # 3. Test Sliding Window Idle Limit (Expired session)
        sess.expires_at = datetime.datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(SessionExpired):
            verify_session(db, session_id)
            
        # Session should be deleted from database after expiration check failure
        db_sess = db.query(UserSession).filter(UserSession.session_id == session_id).first()
        assert db_sess is None
        
        # 4. Test Absolute Cap Limit (12-hour limit)
        sess2 = create_session(db, user_id)
        sess2_id = sess2.session_id
        # Backdate created_at to 12 hours ago
        sess2.created_at = datetime.datetime.now(UTC) - timedelta(hours=12, seconds=1)
        db.commit()
        
        with pytest.raises(SessionExpired):
            verify_session(db, sess2_id)
            
        # Session should be deleted from database
        db_sess2 = db.query(UserSession).filter(UserSession.session_id == sess2_id).first()
        assert db_sess2 is None
        
        # 5. Test Delete Session
        sess3 = create_session(db, user_id)
        sess3_id = sess3.session_id
        delete_session(db, sess3_id)
        db_sess3 = db.query(UserSession).filter(UserSession.session_id == sess3_id).first()
        assert db_sess3 is None
    finally:
        db.close()

def test_lockout_rate_limiting():
    print("--- Test: Lockout Rate Limiting ---")
    db = SessionLocal()
    try:
        username = "lockout_user"
        db.query(LoginAttempt).filter(LoginAttempt.username == username).delete()
        db.commit()
        
        # 1. Try 4 failed login attempts (should not lock)
        for i in range(4):
            try:
                handle_db_lockout(username, db, success=False)
            except HTTPException:
                pytest.fail("Should not lock on 4 attempts")
                
        # Check attempts count in DB
        attempt = db.query(LoginAttempt).filter(LoginAttempt.username == username).first()
        assert attempt.attempts == 4
        assert attempt.locked_until is None
        
        # 2. 5th failed attempt should lock
        with pytest.raises(HTTPException) as excinfo:
            handle_db_lockout(username, db, success=False)
        assert excinfo.value.status_code == 423
        assert "locked" in excinfo.value.detail.lower()
        
        # 3. Subsequent check/attempt when locked should immediately raise 423
        with pytest.raises(HTTPException) as excinfo:
            handle_db_lockout(username, db, success=False)
        assert excinfo.value.status_code == 423
        
        # 4. Success should clear lockout after expiry, but while locked success raises lockout error first
        with pytest.raises(HTTPException):
            handle_db_lockout(username, db, success=True)
            
        # 5. Fast-forward past 15 min lockout
        attempt.locked_until = datetime.datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        
        # Calling handle_db_lockout(username, db, success=True) now should clear the lockout
        handle_db_lockout(username, db, success=True)
        attempt_after = db.query(LoginAttempt).filter(LoginAttempt.username == username).first()
        assert attempt_after is None
    finally:
        db.close()

def test_fastapi_dependencies():
    print("--- Test: FastAPI get_current_user and require_role ---")
    db = SessionLocal()
    try:
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            username="dep_user",
            password_hash=hash_password("pw"),
            display_name="Dep User",
            role="operator"
        )
        db.add(user)
        db.commit()
        
        # Create session
        sess = create_session(db, user_id)
        session_id = sess.session_id
        
        # Mock Request
        request = MagicMock()
        request.cookies = {"session_id": session_id}
        
        # Call dependency get_current_user
        current_user = get_current_user(request, db)
        assert current_user.id == user_id
        
        # Test require_role factory
        op_dep = require_role("operator", "admin")
        res_user = op_dep(current_user)
        assert res_user.id == user_id
        
        # Admin role check should fail (raise HTTP 403)
        admin_dep = require_role("admin")
        with pytest.raises(HTTPException) as excinfo:
            admin_dep(current_user)
        assert excinfo.value.status_code == 403
    finally:
        db.close()

if __name__ == "__main__":
    test_password_hashing()
    test_create_admin_user_cli_and_db()
    test_session_management()
    test_lockout_rate_limiting()
    test_fastapi_dependencies()
    print("=== ALL AUTH WORKER TESTS PASSED SUCCESSFULLY! ===")
