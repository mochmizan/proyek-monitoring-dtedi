import uuid
from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import api
from app.services.activity_logger import should_log_activity, log_user_activity
from auth import hash_password
from databasev5 import Base, engine, get_db
from modelsv5 import ActivityLog, User, dev_table, hub_table, rooms


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    api.state.limiter.enabled = False
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    api.dependency_overrides[get_db] = override_get_db
    with TestClient(api) as c:
        yield c
    api.dependency_overrides.clear()


@pytest.fixture
def seed_users(db_session):
    users = [
        ("testadmin", "admin123", "admin"),
        ("testoperator", "operator123", "operator"),
        ("testviewer", "viewer123", "viewer"),
    ]
    created = {}
    for uname, pwd, role in users:
        u = db_session.query(User).filter(User.username == uname).first()
        if not u:
            u = User(
                id=str(uuid.uuid4()),
                username=uname,
                password_hash=hash_password(pwd),
                display_name=f"Test {role.title()}",
                role=role,
                is_active=True,
            )
            db_session.add(u)
        created[role] = u
    db_session.commit()
    return created


def test_should_log_activity_rbac_matrix():
    """Verify strict RBAC evaluation logic."""
    # 1. Global Rule: Login and Logout must be logged for ALL roles
    for role in ["admin", "operator", "viewer", "guest", None]:
        assert should_log_activity(role, "Login", "auth") is True
        assert should_log_activity(role, "Logout", "auth") is True
        assert should_log_activity(role, "login", "any_cat") is True
        assert should_log_activity(role, "logout", "any_cat") is True

    # 2. Viewer Role: CANNOT log any non-auth activities
    assert should_log_activity("viewer", "View Dashboard", "view") is False
    assert should_log_activity("viewer", "View Telemetry", "view") is False
    assert should_log_activity("viewer", "Kontrol AC", "device_control") is False
    assert should_log_activity("viewer", "Edit Room", "config") is False

    # 3. Operator Role: CAN ONLY log device_control (and auth)
    assert should_log_activity("operator", "Turn on AC", "device_control") is True
    assert should_log_activity("operator", "Start Genset", "device_control") is True
    assert should_log_activity("operator", "Edit Room", "config") is False
    assert should_log_activity("operator", "Create User", "account_management") is False
    assert should_log_activity("operator", "View Alerts", "view") is False

    # 4. Admin Role: Can log device_control, config, account_management, system_adjustment
    assert should_log_activity("admin", "Turn on AC", "device_control") is True
    assert should_log_activity("admin", "Reset FSM", "device_control") is True
    assert should_log_activity("admin", "Membuat ruangan baru", "config") is True
    assert should_log_activity("admin", "Menyetujui perangkat", "config") is True
    assert should_log_activity("admin", "Menambahkan akun", "account_management") is True
    assert should_log_activity("admin", "Adjust Settings", "system_adjustment") is True


def test_direct_log_user_activity_persistence(db_session, seed_users):
    """Verify log_user_activity writes valid rows into the database."""
    viewer = seed_users["viewer"]
    admin = seed_users["admin"]
    operator = seed_users["operator"]

    # Viewer non-auth action should be suppressed
    suppressed = log_user_activity(
        db_session,
        user=viewer,
        action="View Room Map",
        category="view",
    )
    assert suppressed is None

    # Viewer Login should be logged
    log1 = log_user_activity(
        db_session,
        user=viewer,
        action="Login",
        category="auth",
        details={"ip": "127.0.0.1"},
    )
    assert log1 is not None
    assert log1.user_name == "testviewer"
    assert log1.role == "viewer"
    assert log1.activity["action"] == "Login"
    assert log1.activity["details"] == {"ip": "127.0.0.1"}
    assert log1.created_at is not None

    # Operator device control should be logged
    log2 = log_user_activity(
        db_session,
        user=operator,
        action="Kontrol AC (turn_on)",
        category="device_control",
        details={"target": "ac1", "mode": "cool"},
    )
    assert log2 is not None
    assert log2.user_name == "testoperator"
    assert log2.role == "operator"
    assert log2.activity["action"] == "Kontrol AC (turn_on)"

    # Admin configuration should be logged
    log3 = log_user_activity(
        db_session,
        user=admin,
        action="Mengubah threshold alert perangkat",
        category="config",
        details={"dev_id": "ts_01", "warning": 29.0},
    )
    assert log3 is not None
    assert log3.user_name == "testadmin"
    assert log3.role == "admin"
    assert log3.activity["category"] == "config"


def test_auth_endpoints_generate_activity_logs(client, seed_users, db_session):
    """Test login and logout for Admin, Operator, and Viewer through API."""
    roles = ["admin", "operator", "viewer"]

    for r in roles:
        u = seed_users[r]
        # Login
        res_login = client.post(
            "/api/auth/login",
            json={"username": u.username, "password": f"{r}123"},
        )
        assert res_login.status_code == 200

        # Check DB log for Login
        login_log = (
            db_session.query(ActivityLog)
            .filter(ActivityLog.user_name == u.username, ActivityLog.role == r)
            .order_by(ActivityLog.created_at.desc())
            .first()
        )
        assert login_log is not None
        assert login_log.activity["action"] == "Login"
        assert login_log.activity["category"] == "auth"

        # Logout
        res_logout = client.post("/api/auth/logout")
        assert res_logout.status_code == 200

        # Check DB log for Logout
        logout_log = (
            db_session.query(ActivityLog)
            .filter(ActivityLog.user_name == u.username, ActivityLog.role == r)
            .order_by(ActivityLog.created_at.desc())
            .first()
        )
        assert logout_log is not None
        assert logout_log.activity["action"] == "Logout"


def test_operator_and_admin_device_command_logging(client, seed_users, db_session):
    """Test that device commands create activity logs for both operator and admin."""
    # Seed a test hub and device
    hub = db_session.get(hub_table, "test-hub-activity")
    if not hub:
        hub = hub_table(hub_id="test-hub-activity", hub_name="Activity Hub", hub_key="key123", is_active=True)
        db_session.add(hub)

    dev = db_session.get(dev_table, "dev-test-ats")
    if not dev:
        dev = dev_table(dev_id="dev-test-ats", dev_name="ATS-01", dev_type="ATS", hub_id="test-hub-activity", is_active=True)
        db_session.add(dev)
    db_session.commit()

    # Login as Operator
    client.post("/api/auth/login", json={"username": "testoperator", "password": "operator123"})

    # Operator sends ATS command
    cmd_res = client.post(
        "/api/devices/dev-test-ats/command",
        json={"mode": "manual", "start_genset": "on"},
    )
    assert cmd_res.status_code == 200

    # Verify ActivityLog row created for operator
    op_log = (
        db_session.query(ActivityLog)
        .filter(ActivityLog.user_name == "testoperator", ActivityLog.role == "operator")
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    assert op_log is not None
    assert op_log.activity["category"] == "device_control"
    assert "Genset (on)" in op_log.activity["action"]
    assert op_log.activity["details"]["dev_id"] == "dev-test-ats"

    client.post("/api/auth/logout")

    # Login as Admin
    client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})

    # Admin sends Reset FSM command
    reset_res = client.post(
        "/api/devices/dev-test-ats/command",
        json={"reset": "rst"},
    )
    assert reset_res.status_code == 200

    # Verify ActivityLog row created for admin reset
    admin_log = (
        db_session.query(ActivityLog)
        .filter(ActivityLog.user_name == "testadmin", ActivityLog.role == "admin")
        .order_by(ActivityLog.created_at.desc())
        .first()
    )
    assert admin_log is not None
    assert admin_log.activity["action"] == "Reset Hardware FSM"
    assert admin_log.activity["category"] == "device_control"
    assert admin_log.activity["details"]["is_reset"] is True


def test_admin_config_logging_and_activity_logs_endpoint(client, seed_users, db_session):
    """Test admin configuration actions and the activity logs retrieval endpoint."""
    # Login as Admin
    client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})

    # Create a room
    room_res = client.post(
        "/api/rooms",
        json={"name": f"Room-Activity-{uuid.uuid4().hex[:6]}"},
    )
    assert room_res.status_code == 201

    # Query Activity Logs endpoint
    logs_res = client.get("/api/admin/users/activity-logs?limit=10")
    assert logs_res.status_code == 200
    data = logs_res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] > 0

    # Confirm latest log contains room creation
    latest = data["items"][0]
    assert latest["user_name"] == "testadmin"
    assert latest["role"] == "admin"
    assert "activity" in latest
    assert "action" in latest["activity"]
