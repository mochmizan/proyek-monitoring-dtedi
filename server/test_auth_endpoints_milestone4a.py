# test_auth_endpoints_milestone4a.py
import os
import sys
import uuid
import logging
import datetime
from datetime import UTC
import pytest
from fastapi.testclient import TestClient

# 1. Force test database
os.environ["DATABASE_URL"] = "sqlite:///./test_auth_endpoints.db"
os.environ["SERVER_USER"] = "testadmin"
os.environ["PASSWORD_USER"] = "testpass"

# Clean old database if exists
if os.path.exists("./test_auth_endpoints.db"):
    try:
        os.remove("./test_auth_endpoints.db")
    except Exception:
        pass

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import User, dev_table, hub_table
from auth import hash_password
from app.main import api

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    db = SessionLocal()
    # Create test users
    admin = User(
        id="user-admin-id",
        username="admin_test",
        password_hash=hash_password("admin123"),
        display_name="Test Admin",
        role="admin"
    )
    operator = User(
        id="user-operator-id",
        username="operator_test",
        password_hash=hash_password("operator123"),
        display_name="Test Operator",
        role="operator"
    )
    viewer = User(
        id="user-viewer-id",
        username="viewer_test",
        password_hash=hash_password("viewer123"),
        display_name="Test Viewer",
        role="viewer"
    )
    db.add_all([admin, operator, viewer])
    db.commit()
    db.close()
    yield

def test_login_success():
    # Login with admin_test (lowercase check)
    payload = {"username": "ADMIN_TEST", "password": "admin123"}
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "admin_test"
    assert data["display_name"] == "Test Admin"
    assert data["role"] == "admin"
    assert "session_id" in response.cookies

def test_login_failure():
    # Wrong password
    payload = {"username": "admin_test", "password": "wrongpassword"}
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"

    # Non-existent user
    payload = {"username": "non_existent", "password": "somepassword"}
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"

def test_lockout_mechanism():
    # Trigger 5 failures on lockout_user
    username = "lockout_user"
    # Note: lockout_user does not exist, but lockout tracking runs anyway to prevent username enumeration timing attacks.
    payload = {"username": username, "password": "badpassword"}
    
    # First 4 attempts fail with 401
    for _ in range(4):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401

    # 5th attempt fails with 423
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 423
    assert "locked" in response.json()["detail"].lower()

    # 6th attempt (even with correct username if it existed) still fails with 423
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 423

def test_auth_me_unauthorized():
    client.cookies.clear()
    response = client.get("/api/auth/me")
    # Custom exception handler should clear cookie and return 401
    assert response.status_code == 401
    assert "session expired or invalid" in response.json()["detail"].lower()

def test_auth_me_authorized():
    # Login first
    login_res = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    assert login_res.status_code == 200
    session_id = login_res.cookies.get("session_id")
    assert session_id is not None

    # Get me
    response = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "operator_test"
    assert data["role"] == "operator"


def test_csrf_token_endpoint_is_authenticated_and_not_cached():
    client.cookies.clear()
    unauthorized = client.get("/api/auth/csrf-token")
    assert unauthorized.status_code == 401

    login_res = client.post(
        "/api/auth/login",
        json={"username": "operator_test", "password": "operator123"},
    )
    session_id = login_res.cookies.get("session_id")
    token_res = client.get("/api/auth/csrf-token", cookies={"session_id": session_id})

    assert token_res.status_code == 200
    assert len(token_res.json()["csrf_token"]) == 64
    assert token_res.headers["cache-control"] == "no-store"
    assert token_res.headers["pragma"] == "no-cache"


def test_csrf_token_from_another_session_is_rejected():
    first_login = client.post(
        "/api/auth/login",
        json={"username": "operator_test", "password": "operator123"},
    )
    first_session = first_login.cookies.get("session_id")
    first_token = client.get(
        "/api/auth/csrf-token",
        cookies={"session_id": first_session},
    ).json()["csrf_token"]

    second_login = client.post(
        "/api/auth/login",
        json={"username": "operator_test", "password": "operator123"},
    )
    second_session = second_login.cookies.get("session_id")
    response = client.post(
        "/api/auth/logout",
        cookies={"session_id": second_session},
        headers={"X-CSRF-Token": first_token},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_TOKEN_INVALID"


def test_authenticated_mutation_without_csrf_token_is_rejected():
    login_res = client.post(
        "/api/auth/login",
        json={"username": "operator_test", "password": "operator123"},
    )
    session_id = login_res.cookies.get("session_id")
    response = client.post(
        "/api/auth/logout",
        cookies={"session_id": session_id},
        headers={"X-CSRF-Token": ""},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_TOKEN_MISSING"

def test_logout():
    # Login first
    login_res = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    session_id = login_res.cookies.get("session_id")

    # Logout
    logout_res = client.post("/api/auth/logout", cookies={"session_id": session_id})
    assert logout_res.status_code == 200
    assert logout_res.json() == {"status": "logged_out"}
    # session_id cookie should be cleared (its value set to empty or deleted)
    assert logout_res.cookies.get("session_id") in [None, ""]

    # Verify session is deleted (cannot access me anymore)
    me_res = client.get("/api/auth/me", cookies={"session_id": session_id})
    assert me_res.status_code == 401

def test_admin_endpoints_guard():
    # Login admin
    admin_login = client.post("/api/auth/login", json={"username": "admin_test", "password": "admin123"})
    admin_sid = admin_login.cookies.get("session_id")

    # Login operator
    op_login = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    op_sid = op_login.cookies.get("session_id")

    # 1. /api/admin/hubs
    hub_payload = {"HUB_ID": "HUB_4A_TEST", "HUB_NAME": "Test Hub 4A", "HUB_KEY": "secret"}
    
    # Deny Operator
    res = client.post("/api/admin/hubs", json=hub_payload, cookies={"session_id": op_sid})
    assert res.status_code == 403
    assert res.json()["detail"] == "Operation not permitted"

    # Allow Admin
    res = client.post("/api/admin/hubs", json=hub_payload, cookies={"session_id": admin_sid})
    assert res.status_code == 200
    assert res.json()["status"] == "hub_registered"

    # 2. /api/devices/{id}/approve
    # Let's seed a device first
    db = SessionLocal()
    dev = dev_table(dev_id="DEV_TEST_4A", dev_name="Test Dev", dev_type="TS", hub_id="HUB_4A_TEST", is_active=False)
    db.add(dev)
    db.commit()
    db.close()

    # Deny Operator
    res = client.post("/api/devices/DEV_TEST_4A/approve", cookies={"session_id": op_sid})
    assert res.status_code == 403

    # Allow Admin
    res = client.post("/api/devices/DEV_TEST_4A/approve", cookies={"session_id": admin_sid})
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

def test_device_command_guards():
    # Login admin
    admin_login = client.post("/api/auth/login", json={"username": "admin_test", "password": "admin123"})
    admin_sid = admin_login.cookies.get("session_id")

    # Login operator
    op_login = client.post("/api/auth/login", json={"username": "operator_test", "password": "operator123"})
    op_sid = op_login.cookies.get("session_id")

    # Login viewer (neither admin nor operator)
    viewer_login = client.post("/api/auth/login", json={"username": "viewer_test", "password": "viewer123"})
    viewer_sid = viewer_login.cookies.get("session_id")

    # 1. Reset command (admin only)
    reset_payload = {"reset": True}
    
    # Deny Viewer
    res = client.post("/api/devices/DEV_TEST_4A/command", json=reset_payload, cookies={"session_id": viewer_sid})
    assert res.status_code == 403

    # Deny Operator
    res = client.post("/api/devices/DEV_TEST_4A/command", json=reset_payload, cookies={"session_id": op_sid})
    assert res.status_code == 403
    assert res.json()["detail"] == "Reset action requires admin role"

    # Allow Admin -> Should check device existence (or fail model validation but pass role guard)
    res = client.post("/api/devices/DEV_TEST_4A/command", json=reset_payload, cookies={"session_id": admin_sid})
    assert res.status_code != 403

    # 2. Non-reset command (admin or operator)
    normal_payload = {"mode": "manual"}
    
    # Deny Viewer
    res = client.post("/api/devices/DEV_TEST_4A/command", json=normal_payload, cookies={"session_id": viewer_sid})
    assert res.status_code == 403
    assert res.json()["detail"] == "Operation not permitted"

    # Allow Operator
    res = client.post("/api/devices/DEV_TEST_4A/command", json=normal_payload, cookies={"session_id": op_sid})
    assert res.status_code != 403

    # Allow Admin
    res = client.post("/api/devices/DEV_TEST_4A/command", json=normal_payload, cookies={"session_id": admin_sid})
    assert res.status_code != 403
