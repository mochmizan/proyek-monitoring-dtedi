import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.routers import admin_users as admin_users_router
from app.core.csrf import create_csrf_token
from app.main import api
from auth import hash_password, verify_password_safe
from databasev5 import Base, get_db
from modelsv5 import ActivityLog, User, UserAuditLog, UserSession


@pytest.fixture()
def user_management_context():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = test_session()
    admin = User(
        id=str(uuid.uuid4()),
        username="mutation-admin",
        password_hash=hash_password("admin-password"),
        display_name="Mutation Admin",
        role="admin",
        is_active=True,
    )
    session_id = str(uuid.uuid4())
    db.add(admin)
    db.add(
        UserSession(
            session_id=session_id,
            user_id=admin.id,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )
    admin_id = admin.id
    db.commit()
    db.close()

    def override_get_db():
        request_db = test_session()
        try:
            yield request_db
        except Exception:
            request_db.rollback()
            raise
        finally:
            request_db.close()

    api.dependency_overrides[get_db] = override_get_db
    client = TestClient(api, raise_server_exceptions=False)
    client.cookies.set("session_id", session_id)
    client.headers["X-CSRF-Token"] = create_csrf_token(session_id)

    try:
        yield client, test_session, admin_id
    finally:
        client.close()
        api.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_create_user_returns_temp_password_and_persists_logs(user_management_context):
    client, test_session, admin_id = user_management_context

    response = client.post(
        "/api/admin/users",
        json={
            "username": "created_user",
            "display_name": "Created User",
            "role": "viewer",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["username"] == "created_user"
    assert payload["must_change_password"] is True
    assert payload["temp_password"]

    db = test_session()
    try:
        created_user = db.query(User).filter(User.username == "created_user").one()
        assert verify_password_safe(created_user.password_hash, payload["temp_password"])
        assert db.query(UserAuditLog).filter_by(
            actor_id=admin_id,
            target_user_id=created_user.id,
            action="CREATE_USER",
            status="SUCCESS",
        ).count() == 1
        assert db.query(ActivityLog).filter_by(
            user_id=admin_id,
            user_name="mutation-admin",
        ).count() == 1
    finally:
        db.close()


def test_reset_password_returns_temp_password_and_revokes_sessions(user_management_context):
    client, test_session, admin_id = user_management_context
    db = test_session()
    target = User(
        id=str(uuid.uuid4()),
        username="reset-target",
        password_hash=hash_password("old-password"),
        display_name="Reset Target",
        role="operator",
        is_active=True,
    )
    target_session_id = str(uuid.uuid4())
    db.add(target)
    db.add(
        UserSession(
            session_id=target_session_id,
            user_id=target.id,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )
    db.commit()
    target_id = target.id
    old_hash = target.password_hash
    db.close()

    response = client.post(f"/api/admin/users/{target_id}/reset-password")

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "reset-target"
    assert payload["must_change_password"] is True
    assert payload["temp_password"]

    db = test_session()
    try:
        reset_user = db.get(User, target_id)
        assert reset_user.password_hash != old_hash
        assert verify_password_safe(reset_user.password_hash, payload["temp_password"])
        assert db.get(UserSession, target_session_id) is None
        assert db.query(UserAuditLog).filter_by(
            actor_id=admin_id,
            target_user_id=target_id,
            action="RESET_PASSWORD",
            status="SUCCESS",
        ).count() == 1
        assert db.query(ActivityLog).filter_by(
            user_id=admin_id,
            user_name="mutation-admin",
        ).count() == 1
    finally:
        db.close()


def test_create_user_rolls_back_when_activity_logging_fails(
    user_management_context,
    monkeypatch,
):
    client, test_session, _ = user_management_context

    def fail_activity_log(*args, **kwargs):
        raise RuntimeError("simulated activity log failure")

    monkeypatch.setattr(admin_users_router, "log_user_activity", fail_activity_log)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "rolled_back_user",
            "display_name": "Rolled Back User",
            "role": "viewer",
        },
    )

    assert response.status_code == 500

    db = test_session()
    try:
        assert db.query(User).filter(User.username == "rolled_back_user").count() == 0
        assert db.query(UserAuditLog).filter_by(action="CREATE_USER").count() == 0
    finally:
        db.close()


def test_reset_password_rolls_back_when_activity_logging_fails(
    user_management_context,
    monkeypatch,
):
    client, test_session, _ = user_management_context
    db = test_session()
    target = User(
        id=str(uuid.uuid4()),
        username="rollback-reset-target",
        password_hash=hash_password("unchanged-password"),
        display_name="Rollback Reset Target",
        role="viewer",
        is_active=True,
        must_change_password=False,
    )
    target_session_id = str(uuid.uuid4())
    db.add(target)
    db.add(
        UserSession(
            session_id=target_session_id,
            user_id=target.id,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )
    db.commit()
    target_id = target.id
    original_hash = target.password_hash
    db.close()

    def fail_activity_log(*args, **kwargs):
        raise RuntimeError("simulated activity log failure")

    monkeypatch.setattr(admin_users_router, "log_user_activity", fail_activity_log)

    response = client.post(f"/api/admin/users/{target_id}/reset-password")

    assert response.status_code == 500

    db = test_session()
    try:
        unchanged_user = db.get(User, target_id)
        assert unchanged_user.password_hash == original_hash
        assert unchanged_user.must_change_password is False
        assert db.get(UserSession, target_session_id) is not None
        assert db.query(UserAuditLog).filter_by(
            target_user_id=target_id,
            action="RESET_PASSWORD",
        ).count() == 0
    finally:
        db.close()
