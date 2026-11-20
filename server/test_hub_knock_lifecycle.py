# test_hub_knock_lifecycle.py
"""Test Suite for Raspberry Pi Knock & Approval/Decline Lifecycle.

Requirement:
- Disable upfront blocking of unknown hubs.
- Automatically register new knocking hubs as pending_approval so they appear on dashboard.
- Hub receives 403 (quarantined) until approved.
- If approved: hub becomes active (online) and can stream telemetry.
- If declined: hub is blocked with status="blocked" and strictly rejected with 403.
"""

import os
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_knock.db"
os.environ["HUB_BOOTSTRAP_KEY"] = "bootstrap_secret_test"
os.environ["CSRF_SECRET"] = "a" * 32

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import User, UserSession, LoginAttempt, hub_table, dev_table
from auth import hash_password
from app.dependencies import hub_auth_cache
from app.main import api

client = TestClient(api)
api.state.limiter.enabled = False


@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    db = SessionLocal()
    try:
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(dev_table).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Seed Root (Superadmin) user
        admin = User(
            id="user-admin-knock",
            username="admin_knock",
            password_hash=hash_password("adminpass123"),
            display_name="Admin Knock",
            role="root",
            is_active=True,
        )
        # Seed Operator user
        operator = User(
            id="user-operator-knock",
            username="operator_knock",
            password_hash=hash_password("operatorpass123"),
            display_name="Operator Knock",
            role="operator",
            is_active=True,
        )
        db.add_all([admin, operator])
        db.commit()
    finally:
        db.close()
    hub_auth_cache.clear()


def get_admin_session() -> tuple[dict, str]:
    """Helper to log in as admin and obtain session cookie + CSRF token."""
    login_res = client.post(
        "/api/auth/login",
        json={"username": "admin_knock", "password": "adminpass123"},
    )
    assert login_res.status_code == 200, login_res.text
    session_id = login_res.cookies["session_id"]
    csrf_res = client.get("/api/auth/csrf-token", cookies={"session_id": session_id})
    assert csrf_res.status_code == 200, csrf_res.text
    csrf_token = csrf_res.json()["csrf_token"]
    return {"session_id": session_id}, csrf_token


# ===========================================================================
# 1. KNOCK / AUTO-REGISTRATION INTO PENDING_APPROVAL
# ===========================================================================

def test_unknown_hub_knock_auto_registration():
    """An unknown Raspberry Pi contacts the server for the first time.
    Instead of being blocked/discarded, it is auto-registered as pending_approval
    and quarantined with HTTP 403."""
    hub_auth_cache.clear()
    hub_id = "raspi-lab-knock-01"
    hub_key = "secure_edge_key_12345"

    headers = {
        "X-Hub-ID": hub_id,
        "X-Hub-Key": hub_key,
    }

    # Knock request via hub commands endpoint
    resp = client.get("/api/hub/commands", headers=headers)
    assert resp.status_code == 403
    data = resp.json()
    assert "Pending Approval" in data.get("detail", "")

    # Verify database persistence
    db = SessionLocal()
    try:
        hub = db.get(hub_table, hub_id)
        assert hub is not None
        assert hub.hub_id == hub_id
        assert hub.hub_name == hub_id
        assert hub.is_active is False
        assert hub.status == "pending_approval"
        assert hub.hub_key == hub_key
        assert hub.created_at is not None
        assert hub.last_seen is not None
    finally:
        db.close()


def test_pending_hub_stays_quarantined_on_subsequent_requests():
    """While pending approval, subsequent requests must continue to return 403."""
    headers = {
        "X-Hub-ID": "raspi-lab-knock-01",
        "X-Hub-Key": "secure_edge_key_12345",
    }
    resp = client.get("/api/hub/commands", headers=headers)
    assert resp.status_code == 403
    assert "Pending Approval" in resp.json().get("detail", "")


# ===========================================================================
# 2. DASHBOARD REFLECTION (PENDING_APPROVAL VISIBILITY)
# ===========================================================================

def test_dashboard_lists_pending_hub():
    """Admin dashboard lists all hubs, including those pending approval."""
    cookies, _ = get_admin_session()
    resp = client.get("/api/hubs", cookies=cookies)
    assert resp.status_code == 200
    hubs = resp.json()
    pending = [h for h in hubs if h["hub_id"] == "raspi-lab-knock-01"]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending_approval"
    assert pending[0]["is_active"] is False


# ===========================================================================
# 3. ADMIN APPROVAL LIFECYCLE
# ===========================================================================

def test_admin_approve_hub():
    """Admin approves the knocking hub. Hub becomes active and can poll commands and send telemetry."""
    cookies, csrf_token = get_admin_session()
    hub_id = "raspi-lab-knock-01"

    # Approve hub
    resp = client.post(
        f"/api/hubs/{hub_id}/approve",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "approved"
    assert result["hub_id"] == hub_id
    # Since knocking hub provided a valid >=16 char key, zero-touch preserves it!
    assert result["hub_key"] == "secure_edge_key_12345"

    # Verify DB state
    db = SessionLocal()
    try:
        hub = db.get(hub_table, hub_id)
        assert hub.is_active is True
        assert hub.status == "online"

        # Register a paired device for telemetry testing
        dev = dev_table(
            dev_id="TS_KNOCK_01",
            dev_name="Temperature Sensor 1",
            dev_type="TS",
            hub_id=hub_id,
            is_active=True,
        )
        db.add(dev)
        db.commit()
    finally:
        db.close()

    # Now the approved Raspberry Pi polls commands -> Succeeds!
    headers = {
        "X-Hub-ID": hub_id,
        "X-Hub-Key": "secure_edge_key_12345",
    }
    cmd_resp = client.get("/api/hub/commands", headers=headers)
    assert cmd_resp.status_code == 200
    assert isinstance(cmd_resp.json(), list)

    # Telemetry streaming -> Succeeds!
    telemetry = {
        "HUB_NAME": hub_id,
        "DEV_ID": "TS_KNOCK_01",
        "DEV_NAME": "Temperature Sensor 1",
        "DEV_TYPE": "TS",
        "TEMP": 25.1,
        "HUMID": 58.0,
        "HUB_TS": time.time(),
    }
    iot_resp = client.post("/api/iot", json=telemetry, headers=headers)
    assert iot_resp.status_code == 200
    assert iot_resp.json().get("status") in ("received", "success", "telemetry_logged")


def test_cannot_approve_already_active_hub():
    """Approving an already active hub returns HTTP 409 Conflict."""
    cookies, csrf_token = get_admin_session()
    resp = client.post(
        "/api/hubs/raspi-lab-knock-01/approve",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 409


# ===========================================================================
# 4. ADMIN DECLINE AND BLOCK LIFECYCLE
# ===========================================================================

def test_admin_decline_and_block_hub():
    """When an unknown hub knocks and the Admin clicks Decline:
    - Status is set to 'blocked'
    - Future telemetry/command attempts from this hub are strictly rejected with 403."""
    hub_auth_cache.clear()
    bad_hub_id = "raspi-suspicious-02"
    bad_key = "suspicious_key_99999"

    # 1. Suspicious hub knocks
    knock_res = client.get(
        "/api/hub/commands",
        headers={"X-Hub-ID": bad_hub_id, "X-Hub-Key": bad_key},
    )
    assert knock_res.status_code == 403
    assert "Pending Approval" in knock_res.json().get("detail", "")

    # 2. Admin declines the hub
    cookies, csrf_token = get_admin_session()
    decline_res = client.post(
        f"/api/hubs/{bad_hub_id}/decline",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert decline_res.status_code == 200
    assert decline_res.json()["status"] == "blocked"

    # 3. Check dashboard listing reflects 'blocked'
    list_res = client.get("/api/hubs", cookies=cookies)
    hubs = [h for h in list_res.json() if h["hub_id"] == bad_hub_id]
    assert len(hubs) == 1
    assert hubs[0]["status"] == "blocked"
    assert hubs[0]["is_active"] is False

    # 4. Declined hub attempts access -> Strictly blocked!
    blocked_res = client.get(
        "/api/hub/commands",
        headers={"X-Hub-ID": bad_hub_id, "X-Hub-Key": bad_key},
    )
    assert blocked_res.status_code == 403
    assert "diblokir oleh Admin" in blocked_res.json().get("detail", "")


def test_operator_cannot_approve_or_decline():
    """RBAC: Operators cannot approve or decline hubs."""
    # Login as operator
    login_res = client.post(
        "/api/auth/login",
        json={"username": "operator_knock", "password": "operatorpass123"},
    )
    assert login_res.status_code == 200
    op_cookie = {"session_id": login_res.cookies["session_id"]}
    csrf_res = client.get("/api/auth/csrf-token", cookies=op_cookie)
    op_csrf = csrf_res.json()["csrf_token"]

    approve_res = client.post(
        "/api/hubs/raspi-suspicious-02/approve",
        cookies=op_cookie,
        headers={"X-CSRF-Token": op_csrf},
    )
    assert approve_res.status_code == 403

    decline_res = client.post(
        "/api/hubs/raspi-suspicious-02/decline",
        cookies=op_cookie,
        headers={"X-CSRF-Token": op_csrf},
    )
    assert decline_res.status_code == 403


# ===========================================================================
# 5. UNBLOCKING AND VALIDATION TESTS
# ===========================================================================

def test_admin_can_unblock_previously_declined_hub():
    """Admin can approve a previously blocked hub, unblocking it."""
    cookies, csrf_token = get_admin_session()
    bad_hub_id = "raspi-suspicious-02"

    unblock_res = client.post(
        f"/api/hubs/{bad_hub_id}/approve",
        cookies=cookies,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert unblock_res.status_code == 200
    assert unblock_res.json()["status"] == "approved"

    # Hub can now poll commands
    res = client.get(
        "/api/hub/commands",
        headers={"X-Hub-ID": bad_hub_id, "X-Hub-Key": "suspicious_key_99999"},
    )
    assert res.status_code == 200


def test_malformed_hub_id_rejected():
    """Invalid hub IDs (special characters, bad length) are rejected with 400."""
    headers = {
        "X-Hub-ID": "bad*hub!@#$",
        "X-Hub-Key": "valid_length_key_12345",
    }
    res = client.get("/api/hub/commands", headers=headers)
    assert res.status_code == 400
    assert "Format X-Hub-ID tidak valid" in res.json().get("detail", "")
