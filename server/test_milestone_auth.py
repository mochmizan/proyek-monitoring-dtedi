# test_milestone_auth.py
# Verification Test Suite for User Authentication and RBAC Milestone

import os
import sys
import uuid
import logging
import datetime
import time
from datetime import UTC, timedelta
from fastapi.testclient import TestClient

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_milestone_auth.db"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Clean old database if exists
if os.path.exists("./test_milestone_auth.db"):
    try:
        os.remove("./test_milestone_auth.db")
    except Exception as e:
        logging.warning(f"Could not remove old test database: {e}")

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal, engine
from modelsv5 import User, UserSession, LoginAttempt, dev_table, hub_table
from auth import hash_password, verify_password_safe, ph, SessionExpired
from app.main import api

import pytest

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def setup_test_users():
    logging.info("--- Seeding test users & devices ---")
    db = SessionLocal()
    try:
        # Clear existing data for clean module run
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(dev_table).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Create test users
        admin = User(
            id="admin-id-123",
            username="admin_test",
            password_hash=hash_password("admin123"),
            display_name="Test Admin",
            role="admin"
        )
        operator = User(
            id="operator-id-123",
            username="operator_test",
            password_hash=hash_password("operator123"),
            display_name="Test Operator",
            role="operator"
        )
        viewer = User(
            id="viewer-id-123",
            username="viewer_test",
            password_hash=hash_password("viewer123"),
            display_name="Test Viewer",
            role="viewer"
        )
        db.add_all([admin, operator, viewer])

        # Seed default hub and device
        hub = hub_table(hub_id="HUB_TEST", hub_name="Test Hub", hub_key="secret_key", is_active=True)
        dev = dev_table(dev_id="DEV_TEST", dev_name="Test Device", dev_type="TS", hub_id="HUB_TEST", is_active=False)
        db.add_all([hub, dev])

        db.commit()
    finally:
        db.close()

def test_user_creation_and_hashing():
    logging.info("--- Test 1: User Account Hashing (Argon2id) ---")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin_test").first()
        assert user is not None
        # Assert hashed password is not plain-text
        assert user.password_hash != "admin123"
        # Verify using argon2 ph directly
        assert ph.verify(user.password_hash, "admin123") is True
    finally:
        db.close()

def test_session_lifecycle():
    logging.info("--- Test 2: Session Lifecycle (Login, Me, Logout) ---")
    # A. Login Success
    payload = {"username": "admin_test", "password": "admin123"}
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 200, f"Login failed: {res.text}"
    data = res.json()
    assert data["username"] == "admin_test"
    assert data["role"] == "admin"
    assert "session_id" in res.cookies
    session_id = res.cookies.get("session_id")

    # B. Get Profile (Me)
    res_me = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert res_me.status_code == 200, f"Me endpoint failed: {res_me.text}"
    me_data = res_me.json()
    assert me_data["username"] == "admin_test"
    assert me_data["role"] == "admin"

    # C. Logout
    res_logout = client.post("/api/auth/logout", cookies={"session_id": session_id})
    assert res_logout.status_code == 200
    assert res_logout.json() == {"status": "logged_out"}
    assert res_logout.cookies.get("session_id") in [None, ""]

    # D. Me endpoint fails after logout
    res_me_after = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert res_me_after.status_code == 401

def test_rbac_endpoint_protection():
    logging.info("--- Test 3: RBAC Endpoint Protection (Admin Only) ---")
    # Login Operator
    res_op = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    op_sid = res_op.cookies.get("session_id")

    # Login Admin
    res_ad = client.post("/api/auth/login", json={"username": "admin_test", "password": "admin123"})
    ad_sid = res_ad.cookies.get("session_id")

    # Try registering hub as operator (should fail with 403)
    hub_payload = {"HUB_ID": "HUB_NEW", "HUB_NAME": "New Hub", "HUB_KEY": "secret"}
    res = client.post("/api/admin/hubs", json=hub_payload, cookies={"session_id": op_sid})
    assert res.status_code == 403
    assert res.json()["detail"] == "Operation not permitted"

    # Register hub as admin (should succeed)
    res = client.post("/api/admin/hubs", json=hub_payload, cookies={"session_id": ad_sid})
    assert res.status_code == 200

    # Try approving device as operator (should fail with 403)
    res = client.post("/api/devices/DEV_TEST/approve", cookies={"session_id": op_sid})
    assert res.status_code == 403

    # Approve device as admin (should succeed)
    res = client.post("/api/devices/DEV_TEST/approve", cookies={"session_id": ad_sid})
    assert res.status_code == 200

def test_command_routing_role_split():
    logging.info("--- Test 4: Command Routing Action-Level RBAC Split ---")
    # Login Operator
    res_op = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    op_sid = res_op.cookies.get("session_id")

    # Login Admin
    res_ad = client.post("/api/auth/login", json={"username": "admin_test", "password": "admin123"})
    ad_sid = res_ad.cookies.get("session_id")

    # Login Viewer
    res_vw = client.post("/api/auth/login", json={"username": "viewer_test", "password": "viewer123"})
    vw_sid = res_vw.cookies.get("session_id")

    # 1. Reset command (Admin only)
    reset_payload = {"reset": "rst"}
    # Deny Viewer
    res = client.post("/api/devices/DEV_TEST/command", json=reset_payload, cookies={"session_id": vw_sid})
    assert res.status_code == 403
    # Deny Operator
    res = client.post("/api/devices/DEV_TEST/command", json=reset_payload, cookies={"session_id": op_sid})
    assert res.status_code == 403
    assert res.json()["detail"] == "Reset action requires admin role"
    # Allow Admin (fails validation context check since last known mode check is there, but passes role guard)
    res = client.post("/api/devices/DEV_TEST/command", json=reset_payload, cookies={"session_id": ad_sid})
    assert res.status_code != 403

    # 2. Mode command (Admin or Operator)
    mode_payload = {"mode": "manual"}
    # Deny Viewer
    res = client.post("/api/devices/DEV_TEST/command", json=mode_payload, cookies={"session_id": vw_sid})
    assert res.status_code == 403
    # Allow Operator
    res = client.post("/api/devices/DEV_TEST/command", json=mode_payload, cookies={"session_id": op_sid})
    assert res.status_code != 403
    # Allow Admin
    res = client.post("/api/devices/DEV_TEST/command", json=mode_payload, cookies={"session_id": ad_sid})
    assert res.status_code != 403

def test_constant_time_verification():
    logging.info("--- Test 5: Constant-Time Verification check ---")
    # Verify verify_password_safe directly
    # Non-existent user (None stored hash) vs wrong password for existing user
    # Both paths should execute successfully and return False.
    t0 = time.perf_counter()
    res1 = verify_password_safe(None, "random_password")
    t1 = time.perf_counter()
    duration_missing = t1 - t0

    user_hash = hash_password("correct_password")
    t0 = time.perf_counter()
    res2 = verify_password_safe(user_hash, "wrong_password")
    t1 = time.perf_counter()
    duration_wrong = t1 - t0

    assert res1 is False
    assert res2 is False
    logging.info(f"Duration (Missing User Dummy Verify): {duration_missing:.4f}s")
    logging.info(f"Duration (Wrong Password Verify): {duration_wrong:.4f}s")
    # Assert they are of the same order of magnitude (both run Argon2 hashing)
    # Hashing takes > 0.01 seconds. If one was skipped, it would be < 0.001 seconds.
    assert duration_missing > 0.01, "Dummy hash verification was skipped or too fast!"
    assert duration_wrong > 0.01, "Argon2 verification was too fast!"

def test_sliding_expiry_and_absolute_cap():
    logging.info("--- Test 6: Sliding Expiry and 12-Hour Absolute Cap ---")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin_test").first()
        
        # A. Verify sliding works
        sess = UserSession(
            session_id="test-session-slide",
            user_id=user.id,
            expires_at=datetime.datetime.now(UTC) + timedelta(minutes=5),
            created_at=datetime.datetime.now(UTC)
        )
        db.add(sess)
        db.commit()

        # Call get /me -> should slide expires_at
        res = client.get("/api/auth/me", cookies={"session_id": "test-session-slide"})
        assert res.status_code == 200
        
        db.refresh(sess)
        # Expiration should have slid to ~2 hours in future
        time_diff = sess.expires_at.replace(tzinfo=UTC) - datetime.datetime.now(UTC)
        assert time_diff > timedelta(hours=1, minutes=50)

        # B. Verify absolute cap (12 hours limit)
        # Backdate created_at to 12 hours ago
        sess.created_at = datetime.datetime.now(UTC) - timedelta(hours=12, seconds=1)
        db.commit()

        # Call get /me -> should fail (absolute cap exceeded)
        res = client.get("/api/auth/me", cookies={"session_id": "test-session-slide"})
        assert res.status_code == 401
        
        # Session record must be deleted
        db_sess = db.get(UserSession, "test-session-slide")
        assert db_sess is None
    finally:
        db.close()

def test_lockout_mechanism():
    logging.info("--- Test 7: Brute Force Login Lockout (423 Locked) ---")
    username = "lockout_victim"
    payload = {"username": username, "password": "wrong_password"}

    # 1. First 4 bad login attempts should return 401
    for i in range(4):
        res = client.post("/api/auth/login", json=payload)
        assert res.status_code == 401, f"Attempt {i+1} got {res.status_code}"
        assert res.json()["detail"] == "Invalid username or password"

    # 2. 5th attempt should trigger lockout and return 423
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 423

    # 3. 6th attempt (even with correct username/password if they exist) should still return 423
    res = client.post("/api/auth/login", json=payload)
    assert res.status_code == 423

def test_basic_auth_deprecation():
    logging.info("--- Test 8: HTTP Basic Auth Deprecation ---")
    # Old endpoints register_new_hub and approve_device should reject Basic Auth credentials
    res = client.post("/api/admin/hubs", json={}, auth=("caslie", "caslie"))
    # Should reject with 401 unauthenticated because verify_admin is gone and require_role raises SessionExpired -> 401
    assert res.status_code == 401

if __name__ == "__main__":
    try:
        setup_test_users()
        test_user_creation_and_hashing()
        test_session_lifecycle()
        test_rbac_endpoint_protection()
        test_command_routing_role_split()
        test_constant_time_verification()
        test_sliding_expiry_and_absolute_cap()
        test_lockout_mechanism()
        test_basic_auth_deprecation()
        logging.info("=== ALL AUTH MILESTONE VERIFICATION TESTS PASSED SUCCESSFULLY! ===")
    finally:
        # Dispose any active db connections
        engine.dispose()
        
        # Clean up database test file
        if os.path.exists("./test_milestone_auth.db"):
            try:
                os.remove("./test_milestone_auth.db")
                logging.info("Test database cleaned up successfully.")
            except Exception as e:
                logging.warning(f"Could not remove test database at cleanup: {e}")
