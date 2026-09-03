# test_hub_entities_pairing.py
# Test Suite for Hub Entities & Pairing API in HubGate V5

import os
import sys
import uuid
import datetime
from datetime import UTC, timedelta

import pytest
from fastapi.testclient import TestClient

# 1. Force test database & bootstrap key
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"
os.environ["HUB_BOOTSTRAP_KEY"] = "bootstrap_secret_test"

BOOTSTRAP_KEY = os.environ["HUB_BOOTSTRAP_KEY"]

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    rooms, device_threshold_config, temperature_data, ats_data, data_table
)
from auth import hash_password
from app.main import api

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    db = SessionLocal()
    try:
        # Clear tables for clean module isolation
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Create test users with argon2id hashed passwords
        admin = User(
            id="user-admin-hub",
            username="admin_hub",
            password_hash=hash_password("adminpass"),
            display_name="Admin Hub",
            role="admin"
        )
        operator = User(
            id="user-operator-hub",
            username="operator_hub",
            password_hash=hash_password("operatorpass"),
            display_name="Operator Hub",
            role="operator"
        )
        viewer = User(
            id="user-viewer-hub",
            username="viewer_hub",
            password_hash=hash_password("viewerpass"),
            display_name="Viewer Hub",
            role="viewer"
        )
        db.add_all([admin, operator, viewer])

        # Create default active test hub
        hub = hub_table(
            hub_id="HUB_TEST_H1",
            hub_name="Edge Hub Test H1",
            hub_key="secret_key_h1",
            is_active=True
        )
        db.add(hub)

        db.commit()
    finally:
        db.close()


def get_auth_cookies(username: str, password: str) -> dict:
    """Helper to log in and retrieve session cookie."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"session_id": resp.cookies["session_id"]}


def set_hub_last_seen(hub_id: str, last_seen):
    """Helper to directly set a hub's last_seen (None allowed) and reset status."""
    db = SessionLocal()
    try:
        h = db.get(hub_table, hub_id)
        h.last_seen = last_seen
        h.status = "offline"
        db.commit()
    finally:
        db.close()


# ==========================================
# 1. ROLE-BASED ACCESS CONTROL (RBAC)
# ==========================================

def test_rbac_protection():
    admin_cookies = get_auth_cookies("admin_hub", "adminpass")
    operator_cookies = get_auth_cookies("operator_hub", "operatorpass")
    viewer_cookies = get_auth_cookies("viewer_hub", "viewerpass")

    # A. Unauthenticated tests -> 401
    client.cookies.clear()
    assert client.get("/api/hubs").status_code == 401
    assert client.post("/api/hubs/HUB_TEST_H1/approve").status_code == 401
    assert client.post("/api/hubs/HUB_TEST_H1/revoke").status_code == 401

    # B. Viewer role: can read hubs, cannot approve/revoke
    assert client.get("/api/hubs", cookies=viewer_cookies).status_code == 200
    assert client.post("/api/hubs/HUB_TEST_H1/approve", cookies=viewer_cookies).status_code == 403
    assert client.post("/api/hubs/HUB_TEST_H1/revoke", cookies=viewer_cookies).status_code == 403

    # C. Operator role: can read hubs, cannot approve/revoke
    assert client.get("/api/hubs", cookies=operator_cookies).status_code == 200
    assert client.post("/api/hubs/HUB_TEST_H1/approve", cookies=operator_cookies).status_code == 403
    assert client.post("/api/hubs/HUB_TEST_H1/revoke", cookies=operator_cookies).status_code == 403


# ==========================================
# 2. PAIR BOOTSTRAP LIFECYCLE (PENDING -> APPROVE -> PAIRED)
# ==========================================

def test_pair_new_hub_pending_approve_paired():
    admin_cookies = get_auth_cookies("admin_hub", "adminpass")

    # A. Unknown hub with wrong key -> 401
    resp_bad = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_NEW_01", "hub_name": "New Hub 01"},
        headers={"X-Hub-Key": "wrong_bootstrap_key"}
    )
    assert resp_bad.status_code == 401

    # B. No bootstrap key configured case is covered by wrong-key rejection; now correct key -> 202 pending
    resp_pending = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_NEW_01", "hub_name": "New Hub 01"},
        headers={"X-Hub-Key": BOOTSTRAP_KEY}
    )
    assert resp_pending.status_code == 202, f"Pair bootstrap failed: {resp_pending.text}"
    data = resp_pending.json()
    assert data["status"] == "pending_approval"
    assert data["hub_id"] == "HUB_NEW_01"

    # Verify DB: row created inactive with the provided key stored
    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_NEW_01")
        assert h is not None
        assert h.is_active is False
        assert h.hub_name == "New Hub 01"
        assert h.hub_key == BOOTSTRAP_KEY
    finally:
        db.close()

    # C. Pending (inactive) hub pairing again -> still pending approval (202), not duplicated
    resp_again = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_NEW_01", "hub_name": "New Hub 01"},
        headers={"X-Hub-Key": BOOTSTRAP_KEY}
    )
    assert resp_again.status_code == 202
    assert resp_again.json()["status"] == "pending_approval"

    # D. Admin approves -> hub becomes active
    resp_approve = client.post("/api/hubs/HUB_NEW_01/approve", cookies=admin_cookies)
    assert resp_approve.status_code == 200
    assert resp_approve.json() == {"status": "approved", "hub_id": "HUB_NEW_01"}

    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_NEW_01")
        assert h.is_active is True
    finally:
        db.close()

    # E. Approved hub pairs normally with its stored key -> paired + presence stamped
    resp_paired = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_NEW_01", "hub_name": "New Hub 01"},
        headers={"X-Hub-Key": BOOTSTRAP_KEY}
    )
    assert resp_paired.status_code == 200
    assert resp_paired.json()["status"] == "paired"

    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_NEW_01")
        assert h.last_seen is not None
        assert h.status == "online"
    finally:
        db.close()

    # F. Known active hub with wrong key -> 401
    resp_wrong = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_NEW_01", "hub_name": "New Hub 01"},
        headers={"X-Hub-Key": "totally_wrong"}
    )
    assert resp_wrong.status_code == 401


# ==========================================
# 3. REVOKE FLOW (ACCESS DENIED AFTER REVOKE)
# ==========================================

def test_revoke_rejects_hub():
    admin_cookies = get_auth_cookies("admin_hub", "adminpass")

    # A. Approve non-existent hub -> 404
    assert client.post("/api/hubs/HUB_MISSING/revoke", cookies=admin_cookies).status_code == 404
    assert client.post("/api/hubs/HUB_MISSING/approve", cookies=admin_cookies).status_code == 404

    # B. Register an active hub via admin endpoint, then revoke it
    resp_reg = client.post(
        "/api/admin/hubs",
        json={"HUB_ID": "HUB_REVOKED_01", "HUB_NAME": "Revoked Hub", "HUB_KEY": "key_revoked_01"},
        cookies=admin_cookies
    )
    assert resp_reg.status_code == 200

    hub_headers = {"X-Hub-ID": "HUB_REVOKED_01", "X-Hub-Key": "key_revoked_01"}
    assert client.get("/api/devices", headers=hub_headers).status_code == 200

    resp_revoke = client.post("/api/hubs/HUB_REVOKED_01/revoke", cookies=admin_cookies)
    assert resp_revoke.status_code == 200
    assert resp_revoke.json() == {"status": "revoked", "hub_id": "HUB_REVOKED_01"}

    # C. Revoked hub is rejected by verify_hub_identity-protected endpoints
    assert client.get("/api/devices", headers=hub_headers).status_code == 401
    assert client.post(
        "/api/iot",
        json={
            "HUB_NAME": "HUB_REVOKED_01", "DEV_ID": "MAC_X", "DEV_NAME": "X", "DEV_TYPE": "TS",
            "TEMP": 20.0, "HUMID": 50.0
        },
        headers=hub_headers
    ).status_code == 401

    # D. Re-pairing attempt of revoked hub with its own key -> 401 (revoke sticks)
    resp_repair = client.post(
        "/api/hubs/pair",
        json={"hub_id": "HUB_REVOKED_01", "hub_name": "Revoked Hub"},
        headers={"X-Hub-Key": "key_revoked_01"}
    )
    assert resp_repair.status_code == 401

    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_REVOKED_01")
        assert h.is_active is False
    finally:
        db.close()


# ==========================================
# 4. DEVICE GROUPING COUNTS PER HUB
# ==========================================

def test_device_grouping_counts():
    viewer_cookies = get_auth_cookies("viewer_hub", "viewerpass")

    # Seed a second hub and devices across both hubs
    db = SessionLocal()
    try:
        hub2 = hub_table(
            hub_id="HUB_TEST_H2",
            hub_name="Edge Hub Test H2",
            hub_key="secret_key_h2",
            is_active=True
        )
        d1 = dev_table(dev_id="MAC_GRP_1", dev_name="Grp Dev 1", dev_type="TS", hub_id="HUB_TEST_H1", is_active=True)
        d2 = dev_table(dev_id="MAC_GRP_2", dev_name="Grp Dev 2", dev_type="ATS", hub_id="HUB_TEST_H1", is_active=False)
        d3 = dev_table(dev_id="MAC_GRP_3", dev_name="Grp Dev 3", dev_type="AC", hub_id="HUB_TEST_H2", is_active=True)
        orphan = dev_table(dev_id="MAC_GRP_ORPHAN", dev_name="Orphan Dev", dev_type="TS", hub_id=None, is_active=True)
        db.add_all([hub2, d1, d2, d3, orphan])
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/hubs", cookies=viewer_cookies)
    assert resp.status_code == 200
    hubs = {h["hub_id"]: h for h in resp.json()}

    assert "HUB_TEST_H1" in hubs
    assert "HUB_TEST_H2" in hubs

    h1 = hubs["HUB_TEST_H1"]
    assert h1["device_count"] == 2
    assert {d["dev_id"] for d in h1["devices"]} == {"MAC_GRP_1", "MAC_GRP_2"}
    assert all(set(d.keys()) == {"dev_id", "dev_name", "dev_type", "last_seen"} for d in h1["devices"])

    h2 = hubs["HUB_TEST_H2"]
    assert h2["device_count"] == 1
    assert h2["devices"][0]["dev_id"] == "MAC_GRP_3"

    # Orphan device (no hub) must not be counted anywhere
    total_grouped = sum(h["device_count"] for h in hubs.values())
    assert total_grouped == 3

    # Hub response shape check
    assert set(h1.keys()) == {"hub_id", "hub_name", "room", "status", "last_seen", "device_count", "devices"}


# ==========================================
# 5. ONLINE / OFFLINE DETECTION LOGIC
# ==========================================

def test_online_offline_detection():
    viewer_cookies = get_auth_cookies("viewer_hub", "viewerpass")

    # A. Recent heartbeat (within 25s window) -> online
    set_hub_last_seen("HUB_TEST_H1", datetime.datetime.now(UTC))
    resp = client.get("/api/hubs", cookies=viewer_cookies)
    h1 = next(h for h in resp.json() if h["hub_id"] == "HUB_TEST_H1")
    assert h1["status"] == "online"

    # B. Stale heartbeat (> 25s ago) -> offline
    set_hub_last_seen("HUB_TEST_H1", datetime.datetime.now(UTC) - timedelta(seconds=60))
    resp = client.get("/api/hubs", cookies=viewer_cookies)
    h1 = next(h for h in resp.json() if h["hub_id"] == "HUB_TEST_H1")
    assert h1["status"] == "offline"

    # C. Never seen (NULL last_seen) -> offline
    set_hub_last_seen("HUB_TEST_H1", None)
    resp = client.get("/api/hubs", cookies=viewer_cookies)
    h1 = next(h for h in resp.json() if h["hub_id"] == "HUB_TEST_H1")
    assert h1["status"] == "offline"

    # D. verify_hub_identity stamps last_seen on every successful hub request
    old_ts = datetime.datetime.now(UTC) - timedelta(seconds=120)
    set_hub_last_seen("HUB_TEST_H2", old_ts)

    hub_headers = {"X-Hub-ID": "HUB_TEST_H2", "X-Hub-Key": "secret_key_h2"}
    assert client.get("/api/hub/commands", headers=hub_headers).status_code == 200
    assert client.get("/api/devices", headers=hub_headers).status_code == 200

    db = SessionLocal()
    try:
        h = db.get(hub_table, "HUB_TEST_H2")
        stamped = h.last_seen if h.last_seen.tzinfo is not None else h.last_seen.replace(tzinfo=UTC)
        assert (datetime.datetime.now(UTC) - stamped).total_seconds() < 25
    finally:
        db.close()

    # E. After the stamp, hub reports as online
    resp = client.get("/api/hubs", cookies=viewer_cookies)
    h2 = next(h for h in resp.json() if h["hub_id"] == "HUB_TEST_H2")
    assert h2["status"] == "online"
