import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.csrf import create_csrf_token
from app.main import api
from auth import hash_password
from databasev5 import Base, get_db
from modelsv5 import (
    Cluster,
    ClusterRolePermission,
    Device,
    Room,
    User,
    UserClusterMembership,
    UserSession,
)


@pytest.fixture()
def cluster_test_context():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = test_session()

    # 1. Root user
    root_id = str(uuid.uuid4())
    root_user = User(
        id=root_id,
        username="super-root",
        password_hash=hash_password("root123"),
        display_name="Super Root",
        role="root",
        is_active=True,
    )
    root_session_id = str(uuid.uuid4())

    # 2. Regular admin user
    admin_id = str(uuid.uuid4())
    cluster_admin = User(
        id=admin_id,
        username="admin-cluster-a",
        password_hash=hash_password("admin123"),
        display_name="Admin Cluster A",
        role="admin",
        is_active=True,
    )
    admin_session_id = str(uuid.uuid4())

    # 3. Operator user
    operator_id = str(uuid.uuid4())
    cluster_operator = User(
        id=operator_id,
        username="op-cluster-b",
        password_hash=hash_password("operator123"),
        display_name="Operator Cluster B",
        role="operator",
        is_active=True,
    )
    operator_session_id = str(uuid.uuid4())

    db.add_all([root_user, cluster_admin, cluster_operator])

    db.add_all(
        [
            UserSession(
                session_id=root_session_id,
                user_id=root_id,
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            ),
            UserSession(
                session_id=admin_session_id,
                user_id=admin_id,
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            ),
            UserSession(
                session_id=operator_session_id,
                user_id=operator_id,
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            ),
        ]
    )

    # Pre-create Cluster A and Cluster B
    cluster_a_id = str(uuid.uuid4())
    cluster_a = Cluster(
        id=cluster_a_id,
        name="Cluster Alpha",
        location="Gedung Alpha Lantai 1",
        description="Cluster pengujian Alpha",
    )
    cluster_b_id = str(uuid.uuid4())
    cluster_b = Cluster(
        id=cluster_b_id,
        name="Cluster Beta",
        location="Gedung Beta Lantai 2",
        description="Cluster pengujian Beta",
    )
    db.add_all([cluster_a, cluster_b])

    # Assign membership: admin -> cluster_a, operator -> cluster_b
    db.add(
        UserClusterMembership(
            id=str(uuid.uuid4()),
            user_id=admin_id,
            cluster_id=cluster_a_id,
            role="admin",
        )
    )
    db.add(
        UserClusterMembership(
            id=str(uuid.uuid4()),
            user_id=operator_id,
            cluster_id=cluster_b_id,
            role="operator",
        )
    )

    # Rooms and devices
    room_a_id = str(uuid.uuid4())
    room_a = Room(
        id=room_a_id,
        name="Ruang Server A",
        cluster_id=cluster_a_id,
    )
    room_b_id = str(uuid.uuid4())
    room_b = Room(
        id=room_b_id,
        name="Ruang Server B",
        cluster_id=cluster_b_id,
    )
    db.add_all([room_a, room_b])

    dev_a = Device(
        dev_id="TS-0001",
        dev_type="TS",
        room_id=room_a_id,
        cluster_id=cluster_a_id,
        is_active=True,
    )
    dev_b = Device(
        dev_id="TS-0002",
        dev_type="TS",
        room_id=room_b_id,
        cluster_id=cluster_b_id,
        is_active=True,
    )
    db.add_all([dev_a, dev_b])

    db.commit()

    context = {
        "engine": engine,
        "test_session": test_session,
        "root_id": root_id,
        "admin_id": admin_id,
        "operator_id": operator_id,
        "operator_username": "op-cluster-b",
        "root_session_id": root_session_id,
        "admin_session_id": admin_session_id,
        "operator_session_id": operator_session_id,
        "cluster_a_id": cluster_a_id,
        "cluster_b_id": cluster_b_id,
        "room_a_id": room_a_id,
        "room_b_id": room_b_id,
        "dev_a_id": "TS-0001",
        "dev_b_id": "TS-0002",
    }
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

    yield context

    api.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_root_can_create_and_manage_clusters(cluster_test_context):
    client = TestClient(api)
    session_id = cluster_test_context["root_session_id"]
    csrf_token = create_csrf_token(session_id)

    # 1. Root creates a new cluster
    res = client.post(
        "/api/clusters",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={
            "name": "Cluster Gamma",
            "location": "Gedung Gamma Lantai 3",
            "description": "Cluster pengujian Gamma",
        },
    )
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == "Cluster Gamma"
    gamma_id = created["id"]

    # 2. Root lists clusters (paginated response)
    res = client.get(
        "/api/clusters",
        cookies={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # 3. Root updates cluster (PATCH)
    res = client.patch(
        f"/api/clusters/{gamma_id}",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={"name": "Cluster Gamma Updated", "is_active": True},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Cluster Gamma Updated"

    # 4. Root gets cluster detail
    res = client.get(
        f"/api/clusters/{gamma_id}",
        cookies={"session_id": session_id},
    )
    assert res.status_code == 200
    detail = res.json()
    assert detail["name"] == "Cluster Gamma Updated"
    assert "devices" in detail
    assert "rooms" in detail
    assert "members" in detail


def test_non_root_cannot_create_cluster(cluster_test_context):
    client = TestClient(api)
    session_id = cluster_test_context["admin_session_id"]
    csrf_token = create_csrf_token(session_id)

    res = client.post(
        "/api/clusters",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={"name": "Forbidden Cluster"},
    )
    # Admin role is not root, so 403 Forbidden
    assert res.status_code == 403


def test_cluster_membership_management(cluster_test_context):
    client = TestClient(api)
    session_id = cluster_test_context["root_session_id"]
    csrf_token = create_csrf_token(session_id)
    cluster_a_id = cluster_test_context["cluster_a_id"]
    operator_id = cluster_test_context["operator_id"]
    operator_username = cluster_test_context["operator_username"]

    # 1. Root adds operator to cluster A as viewer via /api/memberships
    res = client.post(
        "/api/memberships",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={"user_id": operator_id, "cluster_id": cluster_a_id, "role": "viewer"},
    )
    assert res.status_code == 201
    membership = res.json()
    assert membership["role"] == "viewer"
    assert membership["username"] == operator_username
    membership_id = membership["id"]

    # 2. Get members of cluster A via /api/memberships?cluster_id=...
    res = client.get(
        f"/api/memberships?cluster_id={cluster_a_id}",
        cookies={"session_id": session_id},
    )
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 2

    # 3. Update member's role to operator (PATCH /api/memberships/{id})
    res = client.patch(
        f"/api/memberships/{membership_id}",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={"role": "operator"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "operator"

    # 4. Remove member (DELETE /api/memberships/{id})
    res = client.delete(
        f"/api/memberships/{membership_id}",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
    )
    assert res.status_code == 200


def test_cluster_permission_matrix(cluster_test_context):
    client = TestClient(api)
    session_id = cluster_test_context["root_session_id"]
    csrf_token = create_csrf_token(session_id)
    cluster_a_id = cluster_test_context["cluster_a_id"]

    # 1. Get default permissions for cluster A
    res = client.get(
        f"/api/clusters/{cluster_a_id}/permissions",
        cookies={"session_id": session_id},
    )
    assert res.status_code == 200
    data = res.json()
    matrix = data["permissions"]
    assert "admin" in matrix
    assert "operator" in matrix
    assert "viewer" in matrix
    assert matrix["admin"]["manage_rooms"] is True
    assert matrix["viewer"]["control_devices"] is False

    # 2. Update permissions (e.g. grant control_devices to viewer for this specific cluster)
    updated_viewer = dict(matrix["viewer"])
    updated_viewer["control_devices"] = True

    res = client.put(
        f"/api/clusters/{cluster_a_id}/permissions",
        cookies={"session_id": session_id},
        headers={"x-csrf-token": csrf_token},
        json={"role": "viewer", "permissions": updated_viewer},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 3. Verify updated permissions via GET
    res = client.get(
        f"/api/clusters/{cluster_a_id}/permissions",
        cookies={"session_id": session_id},
    )
    assert res.status_code == 200
    assert res.json()["permissions"]["viewer"]["control_devices"] is True


def test_scoped_devices_and_rooms_isolation(cluster_test_context):
    client = TestClient(api)
    root_session = cluster_test_context["root_session_id"]
    admin_session = cluster_test_context["admin_session_id"]  # Cluster Alpha
    operator_session = cluster_test_context["operator_session_id"]  # Cluster Beta

    # 1. Root sees all devices and all rooms
    res = client.get("/api/devices", cookies={"session_id": root_session})
    assert res.status_code == 200
    devices = res.json()
    assert len(devices) == 2

    res = client.get("/api/rooms", cookies={"session_id": root_session})
    assert res.status_code == 200
    rooms = res.json()
    assert len(rooms) == 2

    # 2. Admin of Cluster Alpha only sees device A and room A
    res = client.get("/api/devices", cookies={"session_id": admin_session})
    assert res.status_code == 200
    admin_devices = res.json()
    assert len(admin_devices) == 1
    assert admin_devices[0]["dev_id"] == "TS-0001"

    res = client.get("/api/rooms", cookies={"session_id": admin_session})
    assert res.status_code == 200
    admin_rooms = res.json()
    assert len(admin_rooms) == 1
    assert admin_rooms[0]["name"] == "Ruang Server A"

    # 3. Operator of Cluster Beta only sees device B and room B
    res = client.get("/api/devices", cookies={"session_id": operator_session})
    assert res.status_code == 200
    op_devices = res.json()
    assert len(op_devices) == 1
    assert op_devices[0]["dev_id"] == "TS-0002"

    res = client.get("/api/rooms", cookies={"session_id": operator_session})
    assert res.status_code == 200
    op_rooms = res.json()
    assert len(op_rooms) == 1
    assert op_rooms[0]["name"] == "Ruang Server B"

    # 4. Cross-cluster access attempt: Admin Alpha accessing device B directly -> 403 Forbidden
    dev_b_id = cluster_test_context["dev_b_id"]
    res = client.get(f"/api/devices/{dev_b_id}", cookies={"session_id": admin_session})
    assert res.status_code == 403


def test_scoped_alerts_isolation(cluster_test_context):
    from modelsv5 import event_log
    client = TestClient(api)
    root_session = cluster_test_context["root_session_id"]
    admin_session = cluster_test_context["admin_session_id"]  # Cluster Alpha
    operator_session = cluster_test_context["operator_session_id"]  # Cluster Beta
    dev_a_id = cluster_test_context["dev_a_id"]
    dev_b_id = cluster_test_context["dev_b_id"]
    room_a_id = cluster_test_context["room_a_id"]
    room_b_id = cluster_test_context["room_b_id"]
    cluster_b_id = cluster_test_context["cluster_b_id"]

    # Insert test events into database
    test_session = cluster_test_context["test_session"]
    db = test_session()
    evt_a = event_log(
        event_id=str(uuid.uuid4()),
        dev_id=dev_a_id,
        room_id=room_a_id,
        metric="temp",
        value=32.5,
        threshold=30.0,
        severity="warning",
        alarm="HIGH_TEMP",
        timestamp=datetime.now(UTC),
    )
    evt_b = event_log(
        event_id=str(uuid.uuid4()),
        dev_id=dev_b_id,
        room_id=room_b_id,
        metric="temp",
        value=38.0,
        threshold=35.0,
        severity="critical",
        alarm="CRITICAL_TEMP",
        timestamp=datetime.now(UTC),
    )
    db.add_all([evt_a, evt_b])
    db.commit()
    db.close()

    # 1. Root sees both alerts
    res = client.get("/api/alerts", cookies={"session_id": root_session})
    assert res.status_code == 200
    assert res.json()["total"] == 2

    # 2. Admin of Cluster Alpha only sees dev_a alert
    res = client.get("/api/alerts", cookies={"session_id": admin_session})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["alerts"][0]["dev_id"] == dev_a_id

    # 3. Operator of Cluster Beta only sees dev_b alert
    res = client.get("/api/alerts", cookies={"session_id": operator_session})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["alerts"][0]["dev_id"] == dev_b_id

    # 4. Admin of Cluster Alpha attempts to filter by Cluster Beta -> 0 alerts
    res = client.get(f"/api/alerts?cluster_id={cluster_b_id}", cookies={"session_id": admin_session})
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_scoped_schedules_isolation(cluster_test_context):
    client = TestClient(api)
    admin_session = cluster_test_context["admin_session_id"]  # Cluster Alpha
    csrf_token = create_csrf_token(admin_session)
    dev_a_id = cluster_test_context["dev_a_id"]
    dev_b_id = cluster_test_context["dev_b_id"]

    # 1. Admin in Cluster Alpha attempts to create schedule for dev_b (Cluster Beta) -> 403 Forbidden
    res = client.post(
        "/api/schedules",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "dev_id": dev_b_id,
            "cron_expr": "0 8 * * *",
            "payload": {"mode": "manual", "start_genset": "on"},
            "enabled": True,
        },
    )
    assert res.status_code == 403

    # 2. Admin in Cluster Alpha creates schedule for dev_a (Cluster Alpha) -> 201 Created
    res = client.post(
        "/api/schedules",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "dev_id": dev_a_id,
            "cron_expr": "0 8 * * *",
            "payload": {"mode": "manual", "start_genset": "on"},
            "enabled": True,
        },
    )
    assert res.status_code == 201


def test_cluster_admin_creation_and_role_persistence(cluster_test_context):
    client = TestClient(api)
    root_session = cluster_test_context["root_session_id"]
    csrf_token = create_csrf_token(root_session)
    cluster_a_id = cluster_test_context["cluster_a_id"]

    # Root creates a new cluster admin assigned to Cluster Alpha
    res = client.post(
        "/api/admin/users",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "username": "new_cluster_admin",
            "display_name": "New Cluster Admin",
            "role": "admin",
            "cluster_id": cluster_a_id,
            "cluster_role": "admin",
        },
    )
    assert res.status_code == 201
    user_data = res.json()
    assert user_data["role"] == "admin"  # NOT "member"
    temp_pass = user_data["temp_password"]

    # New admin logs in
    login_res = client.post(
        "/api/auth/login",
        json={"username": "new_cluster_admin", "password": temp_pass},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["role"] == "admin"
    admin_new_session = login_res.cookies.get("session_id")

    # Call /api/auth/me
    me_res = client.get("/api/auth/me", cookies={"session_id": admin_new_session})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["role"] == "admin"
    assert len(me_data["cluster_memberships"]) == 1
    assert me_data["cluster_memberships"][0]["cluster_id"] == cluster_a_id


def test_cluster_admin_scoping_user_management(cluster_test_context):
    client = TestClient(api)
    admin_session = cluster_test_context["admin_session_id"]  # Admin of Cluster Alpha
    csrf_token = create_csrf_token(admin_session)
    cluster_a_id = cluster_test_context["cluster_a_id"]
    cluster_b_id = cluster_test_context["cluster_b_id"]

    # Cluster Alpha admin creates an operator
    res = client.post(
        "/api/admin/users",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "username": "scoped_op_a",
            "display_name": "Scoped Operator A",
            "role": "operator",
            "cluster_id": cluster_a_id,
            "cluster_role": "operator",
        },
    )
    assert res.status_code == 201
    scoped_op_id = res.json()["id"]

    # Cluster Alpha admin cannot create a root user
    res = client.post(
        "/api/admin/users",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "username": "illegal_root",
            "display_name": "Illegal Root",
            "role": "root",
        },
    )
    assert res.status_code == 403

    # Cluster Alpha admin cannot assign to Cluster Beta
    res = client.post(
        "/api/admin/users",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={
            "username": "illegal_op_b",
            "display_name": "Illegal Op B",
            "role": "operator",
            "cluster_id": cluster_b_id,
        },
    )
    assert res.status_code == 403

    # Cluster Alpha admin can see their scoped operator in user list
    res = client.get("/api/admin/users", cookies={"session_id": admin_session})
    assert res.status_code == 200
    usernames = [u["username"] for u in res.json()["items"]]
    assert "scoped_op_a" in usernames
    assert "op-cluster-b" not in usernames  # Cluster Beta user hidden

    # Cluster Alpha admin can toggle status of their operator
    res = client.patch(
        f"/api/admin/users/{scoped_op_id}/status",
        cookies={"session_id": admin_session},
        headers={"x-csrf-token": csrf_token},
        json={"is_active": False},
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_cluster_rooms_and_devices_management(cluster_test_context):
    client = TestClient(api)
    root_session = cluster_test_context["root_session_id"]
    csrf_token = create_csrf_token(root_session)
    cluster_a_id = cluster_test_context["cluster_a_id"]
    dev_a_id = cluster_test_context["dev_a_id"]

    # 1. Check unassigned resources
    res = client.get("/api/clusters/unassigned-resources", cookies={"session_id": root_session})
    assert res.status_code == 200
    data = res.json()
    assert "rooms" in data
    assert "devices" in data

    # 2. Create room in cluster
    res = client.post(
        f"/api/clusters/{cluster_a_id}/rooms",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
        json={"name": "Ruang Server A1", "floor": 1},
    )
    assert res.status_code == 201
    room = res.json()
    room_id = room["id"]
    assert room["name"] == "Ruang Server A1"
    assert room["cluster_id"] == cluster_a_id

    # 3. Update room name
    res = client.patch(
        f"/api/clusters/{cluster_a_id}/rooms/{room_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
        json={"name": "Ruang Server A1 (Renamed)"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Ruang Server A1 (Renamed)"

    # 4. Update device room assignment
    res = client.patch(
        f"/api/clusters/{cluster_a_id}/devices/{dev_a_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
        json={"room_id": room_id, "name": "Sensor Suhu A1 Utama"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Sensor Suhu A1 Utama"

    # 5. Get cluster members
    members_res = client.get(
        f"/api/clusters/{cluster_a_id}/members",
        cookies={"session_id": root_session},
    )
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) >= 1
    assert any(m["user_id"] == cluster_test_context["admin_id"] for m in members)

    # 6. Unassign device from cluster
    res = client.post(
        f"/api/clusters/{cluster_a_id}/unassign-device?dev_id={dev_a_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
    )
    assert res.status_code == 200

    # 7. Unassign room from cluster
    res = client.post(
        f"/api/clusters/{cluster_a_id}/unassign-room?room_id={room_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
    )
    assert res.status_code == 200

    # 8. Re-assign room and delete it
    res = client.post(
        f"/api/clusters/{cluster_a_id}/assign-room?room_id={room_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
    )
    assert res.status_code == 200

    del_res = client.delete(
        f"/api/clusters/{cluster_a_id}/rooms/{room_id}",
        cookies={"session_id": root_session},
        headers={"x-csrf-token": csrf_token},
    )
    assert del_res.status_code == 200


