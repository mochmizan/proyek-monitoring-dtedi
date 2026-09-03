# test_schedules_regression.py
# Comprehensive Regression Test Suite for Automation Scheduler (Phase 2.0 Safety Gate)

import os
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, LoginAttempt, hub_table, dev_table,
    rooms, pending_commands, schedules
)
from auth import hash_password
from hubgatev5 import api
import app.services.scheduler as scheduler_service
from app.services.scheduler import (
    CANONICAL_TZ,
    _validate_cron_expr,
    get_next_runs,
    human_cron,
    fire_schedule,
    sync_job,
    remove_job,
)

api.state.limiter.enabled = False

ADMIN_CREDS = {"username": "sched_admin", "password": "adminpassword"}
OPERATOR_CREDS = {"username": "sched_operator", "password": "operatorpassword"}
VIEWER_CREDS = {"username": "sched_viewer", "password": "viewerpassword"}


@pytest.fixture(scope="module", autouse=True)
def setup_schedules_db():
    db = SessionLocal()
    try:
        # Clean relevant tables
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(pending_commands).delete()
        db.query(schedules).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Seed users
        admin = User(
            id="user-sched-admin",
            username=ADMIN_CREDS["username"],
            password_hash=hash_password(ADMIN_CREDS["password"]),
            display_name="Schedule Admin",
            role="admin",
        )
        operator = User(
            id="user-sched-operator",
            username=OPERATOR_CREDS["username"],
            password_hash=hash_password(OPERATOR_CREDS["password"]),
            display_name="Schedule Operator",
            role="operator",
        )
        viewer = User(
            id="user-sched-viewer",
            username=VIEWER_CREDS["username"],
            password_hash=hash_password(VIEWER_CREDS["password"]),
            display_name="Schedule Viewer",
            role="viewer",
        )
        db.add_all([admin, operator, viewer])

        # Seed test hub & devices
        hub = hub_table(
            hub_id="HUB_SCHED_01",
            hub_name="Scheduler Test Hub",
            hub_key="secret_sched_key",
            is_active=True,
        )
        db.add(hub)

        dev_ats = dev_table(
            dev_id="ATS_SCHED_01",
            dev_name="ATS Generator Unit",
            dev_type="ATS",
            hub_id="HUB_SCHED_01",
            is_active=True,
        )
        dev_ac = dev_table(
            dev_id="AC_SCHED_01",
            dev_name="AC Server Room",
            dev_type="AC",
            hub_id="HUB_SCHED_01",
            is_active=True,
        )
        db.add_all([dev_ats, dev_ac])
        db.commit()
    finally:
        db.close()


def get_auth_client(creds: dict) -> TestClient:
    """Return a TestClient with isolated authenticated session."""
    client = TestClient(api)
    resp = client.post("/api/auth/login", json=creds)
    assert resp.status_code == 200
    return client


def get_unauth_client() -> TestClient:
    """Return an unauthenticated TestClient."""
    return TestClient(api)


# ============================================================================
# 1. UNIT TESTS: app/services/scheduler.py
# ============================================================================

def test_validate_cron_expr_valid():
    # Standard 5-field crons
    _validate_cron_expr("0 18 * * 0")
    _validate_cron_expr("*/5 * * * *")
    _validate_cron_expr("0 0 1 1 *")
    _validate_cron_expr("30 4 1,15 * 1-5")


def test_validate_cron_expr_empty_or_whitespace():
    with pytest.raises(ValueError, match="cron_expr is required"):
        _validate_cron_expr("")
    with pytest.raises(ValueError, match="cron_expr is required"):
        _validate_cron_expr("   ")


def test_validate_cron_expr_unsupported_shortcuts():
    with pytest.raises(ValueError, match="Unsupported cron shortcut"):
        _validate_cron_expr("@daily")
    with pytest.raises(ValueError, match="Unsupported cron shortcut"):
        _validate_cron_expr("@reboot")
    with pytest.raises(ValueError, match="Unsupported cron shortcut"):
        _validate_cron_expr("@hourly")


def test_validate_cron_expr_field_count():
    with pytest.raises(ValueError, match="must have 5 fields"):
        _validate_cron_expr("* * *")
    with pytest.raises(ValueError, match="must have 5 fields"):
        _validate_cron_expr("* * * * * *")


def test_validate_cron_expr_invalid_values():
    with pytest.raises(ValueError, match="Invalid cron_expr"):
        _validate_cron_expr("65 * * * *")
    with pytest.raises(ValueError, match="Invalid cron_expr"):
        _validate_cron_expr("* 25 * * *")


def test_validate_cron_expr_invalid_timezone():
    with pytest.raises(ValueError, match="Invalid cron_expr"):
        _validate_cron_expr("0 18 * * 0", tz="NonExistent/Timezone")


def test_get_next_runs():
    runs = get_next_runs("0 18 * * 0", tz="Asia/Jakarta", count=3)
    assert len(runs) == 3
    # Verify timezone awareness and chronological order
    jakarta_tz = ZoneInfo("Asia/Jakarta")
    for r in runs:
        assert r.tzinfo is not None
        assert r.astimezone(jakarta_tz).hour == 18
        assert r.astimezone(jakarta_tz).minute == 0
    assert runs[0] < runs[1] < runs[2]

    # Test count parameter
    single_run = get_next_runs("0 18 * * 0", count=1)
    assert len(single_run) == 1

    # Invalid cron returns empty list
    invalid_runs = get_next_runs("invalid cron", count=3)
    assert invalid_runs == []


def test_human_cron():
    assert human_cron("0 18 * * 0") == "At 06:00 PM, only on Sunday"
    # Fallback to trimmed expression if no custom mapping / cron_descriptor
    fallback = human_cron("*/10 * * * *")
    assert fallback in ("*/10 * * * *", "Every 10 minutes")


def test_fire_schedule_and_hub_resolution():
    db = SessionLocal()
    try:
        sched_id = f"sched-test-fire-{uuid.uuid4()}"
        sched = schedules(
            id=sched_id,
            dev_id="ATS_SCHED_01",
            hub_id=None,  # Will test hub resolution fallback
            cron_expr="0 18 * * 0",
            payload={"mode": "manual", "start_genset": "on"},
            tz="Asia/Jakarta",
            enabled=True,
            created_by="sched_admin",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(sched)
        db.commit()

        # Execute fire_schedule
        fire_schedule(sched_id)

        # Verify command created in pending_commands
        cmd = db.query(pending_commands).filter(pending_commands.dev_id == "ATS_SCHED_01").first()
        assert cmd is not None
        assert cmd.hub_id == "HUB_SCHED_01"  # Resolved from dev_table
        assert cmd.payload == {"mode": "manual", "start_genset": "on"}
        assert cmd.status == "pending"

        # Verify schedule.next_run_at was updated
        db.refresh(sched)
        assert sched.next_run_at is not None

        # Clean up command
        db.delete(cmd)
        db.commit()

        # Verify disabled schedule does NOT fire
        sched.enabled = False
        db.commit()
        fire_schedule(sched_id)
        cmd_disabled = db.query(pending_commands).filter(pending_commands.dev_id == "ATS_SCHED_01").first()
        assert cmd_disabled is None

        # Verify non-existent schedule does not raise
        fire_schedule("non-existent-sched-id")
    finally:
        db.close()


def test_sync_job_and_remove_job():
    # Test when scheduler is not running (should be a safe no-op)
    orig_sched = scheduler_service.scheduler
    scheduler_service.scheduler = None
    sync_job("sched-noop", "0 18 * * 0", "Asia/Jakarta", enabled=True)
    remove_job("sched-noop")

    # Now test with a real running BackgroundScheduler
    test_sched = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1})
    test_sched.start()
    scheduler_service.scheduler = test_sched

    try:
        job_id = "schedule-sched-unit-1"
        # 1. Add enabled job
        sync_job("sched-unit-1", "0 18 * * 0", "Asia/Jakarta", enabled=True)
        job = test_sched.get_job(job_id)
        assert job is not None

        # 2. Reschedule job
        sync_job("sched-unit-1", "30 9 * * 1", "Asia/Jakarta", enabled=True)
        job_rescheduled = test_sched.get_job(job_id)
        assert job_rescheduled is not None

        # 3. Disable job removes it from scheduler
        sync_job("sched-unit-1", "30 9 * * 1", "Asia/Jakarta", enabled=False)
        assert test_sched.get_job(job_id) is None

        # 4. remove_job explicit deletion
        sync_job("sched-unit-2", "0 0 * * *", "Asia/Jakarta", enabled=True)
        assert test_sched.get_job("schedule-sched-unit-2") is not None
        remove_job("sched-unit-2")
        assert test_sched.get_job("schedule-sched-unit-2") is None
    finally:
        test_sched.shutdown(wait=False)
        scheduler_service.scheduler = orig_sched


# ============================================================================
# 2. INTEGRATION TESTS: server/app/routers/schedules.py
# ============================================================================

def test_preview_cron_endpoint():
    admin_client = get_auth_client(ADMIN_CREDS)
    unauth_client = get_unauth_client()

    # 1. Successful preview
    resp = admin_client.get(
        "/api/schedules/preview",
        params={"cron_expr": "0 18 * * 0", "tz": "Asia/Jakarta"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cron_expr"] == "0 18 * * 0"
    assert data["tz"] == "Asia/Jakarta"
    assert len(data["next_runs"]) == 3
    assert data["next_run"] == data["next_runs"][0]
    assert "human" in data

    # 2. Unauthenticated request rejected
    resp_unauth = unauth_client.get("/api/schedules/preview", params={"cron_expr": "0 18 * * 0"})
    assert resp_unauth.status_code == 401

    # 3. Invalid cron returns 422
    resp_invalid = admin_client.get(
        "/api/schedules/preview",
        params={"cron_expr": "invalid * *"},
    )
    assert resp_invalid.status_code == 422


def test_create_schedule_rbac_and_validation():
    admin_client = get_auth_client(ADMIN_CREDS)
    operator_client = get_auth_client(OPERATOR_CREDS)
    viewer_client = get_auth_client(VIEWER_CREDS)
    unauth_client = get_unauth_client()

    valid_body = {
        "dev_id": "ATS_SCHED_01",
        "hub_id": "HUB_SCHED_01",
        "cron_expr": "0 18 * * 0",
        "payload": {"mode": "manual", "start_genset": "on"},
        "tz": "Asia/Jakarta",
        "enabled": True,
    }

    # 1. Unauthenticated -> 401
    res_unauth = unauth_client.post("/api/schedules", json=valid_body)
    assert res_unauth.status_code == 401

    # 2. Viewer -> 403
    res_viewer = viewer_client.post("/api/schedules", json=valid_body)
    assert res_viewer.status_code == 403

    # 3. Operator -> 403 (schedules mutation is admin-only)
    res_op = operator_client.post("/api/schedules", json=valid_body)
    assert res_op.status_code == 403

    # 4. Admin -> 201 Created
    res_admin = admin_client.post("/api/schedules", json=valid_body)
    assert res_admin.status_code == 201
    created = res_admin.json()
    assert created["dev_id"] == "ATS_SCHED_01"
    assert created["cron_expr"] == "0 18 * * 0"
    assert created["enabled"] is True
    assert "id" in created

    # 5. Invalid cron expression -> 422
    invalid_cron_body = dict(valid_body, cron_expr="bad_cron")
    res_bad_cron = admin_client.post("/api/schedules", json=invalid_cron_body)
    assert res_bad_cron.status_code == 422

    # 6. Non-whitelisted command payload -> 422
    invalid_payload_body = dict(valid_body, payload={"unauthorized_field": "explode"})
    res_bad_payload = admin_client.post("/api/schedules", json=invalid_payload_body)
    assert res_bad_payload.status_code == 422

    # 7. Non-existent device -> 404
    missing_dev_body = dict(valid_body, dev_id="NON_EXISTENT_DEV")
    res_missing_dev = admin_client.post("/api/schedules", json=missing_dev_body)
    assert res_missing_dev.status_code == 404

    # 8. Non-existent hub -> 404
    missing_hub_body = dict(valid_body, hub_id="NON_EXISTENT_HUB")
    res_missing_hub = admin_client.post("/api/schedules", json=missing_hub_body)
    assert res_missing_hub.status_code == 404


def test_schedule_crud_lifecycle_and_filters():
    admin_client = get_auth_client(ADMIN_CREDS)
    operator_client = get_auth_client(OPERATOR_CREDS)

    # 1. Create AC schedule
    ac_body = {
        "dev_id": "AC_SCHED_01",
        "cron_expr": "0 8 * * 1-5",
        "payload": {"target": "AC1", "action": "ON"},
        "tz": "Asia/Jakarta",
        "enabled": True,
    }
    create_res = admin_client.post("/api/schedules", json=ac_body)
    assert create_res.status_code == 201
    sched = create_res.json()
    sched_id = sched["id"]

    # 2. List schedules (operator can view)
    list_res = operator_client.get("/api/schedules")
    assert list_res.status_code == 200
    all_schedules = list_res.json()
    assert any(s["id"] == sched_id for s in all_schedules)

    # Filter by dev_id
    filter_res = operator_client.get("/api/schedules", params={"dev_id": "AC_SCHED_01"})
    assert filter_res.status_code == 200
    filtered_list = filter_res.json()
    assert all(s["dev_id"] == "AC_SCHED_01" for s in filtered_list)

    # Filter by enabled
    filter_enabled = operator_client.get("/api/schedules", params={"enabled": True})
    assert filter_enabled.status_code == 200

    # 3. Get schedule detail
    get_res = operator_client.get(f"/api/schedules/{sched_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == sched_id
    assert len(get_res.json()["next_runs"]) == 3

    # Get non-existent
    not_found = operator_client.get("/api/schedules/non-existent-sched-id")
    assert not_found.status_code == 404

    # 4. Patch schedule (keep enabled: True for subsequent run-now check)
    # Non-admin rejected
    patch_op = operator_client.patch(
        f"/api/schedules/{sched_id}",
        json={"cron_expr": "0 9 * * 1-5"},
    )
    assert patch_op.status_code == 403

    # Admin patches successfully
    patch_admin = admin_client.patch(
        f"/api/schedules/{sched_id}",
        json={"cron_expr": "0 9 * * 1-5", "enabled": True},
    )
    assert patch_admin.status_code == 200
    updated = patch_admin.json()
    assert updated["cron_expr"] == "0 9 * * 1-5"
    assert updated["enabled"] is True

    # 5. Run-now
    # Operator rejected
    run_op = operator_client.post(f"/api/schedules/{sched_id}/run-now")
    assert run_op.status_code == 403

    # Admin triggers run-now
    run_admin = admin_client.post(f"/api/schedules/{sched_id}/run-now")
    assert run_admin.status_code == 200
    assert run_admin.json()["status"] == "fired"

    # Verify pending command created
    db = SessionLocal()
    try:
        cmd = db.query(pending_commands).filter(pending_commands.dev_id == "AC_SCHED_01").first()
        assert cmd is not None
        assert cmd.payload == {"target": "AC1", "action": "ON"}
        db.delete(cmd)
        db.commit()
    finally:
        db.close()

    # 6. Delete schedule
    # Operator rejected
    del_op = operator_client.delete(f"/api/schedules/{sched_id}")
    assert del_op.status_code == 403

    # Admin deletes
    del_admin = admin_client.delete(f"/api/schedules/{sched_id}")
    assert del_admin.status_code == 200
    assert del_admin.json()["status"] == "deleted"

    # Verify 404 after delete
    get_after_del = admin_client.get(f"/api/schedules/{sched_id}")
    assert get_after_del.status_code == 404
