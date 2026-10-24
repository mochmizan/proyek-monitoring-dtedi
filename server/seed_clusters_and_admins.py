# seed_clusters_and_admins.py
import uuid
import datetime
from datetime import UTC
from databasev5 import SessionLocal
from modelsv5 import (
    Base, Cluster, User, UserClusterMembership, ClusterRolePermission,
    rooms, dev_table, temperature_data, ats_data, data_table, hub_table
)
from auth import hash_password, DEFAULT_PERMISSIONS

def seed_clusters_and_admins():
    db = SessionLocal()
    try:
        now = datetime.datetime.now(UTC)

        # 0. Ensure Hub exists
        hub = db.query(hub_table).filter_by(hub_id="RASPI_HUB_01").first()
        if not hub:
            hub = hub_table(
                hub_id="RASPI_HUB_01",
                hub_name="Default Edge Hub V5",
                hub_key="test-hub-key-v5",
                is_active=True,
                status="online",
                last_seen=now,
            )
            db.add(hub)
            db.commit()

        # 1. Clusters setup
        clusters_info = [
            {
                "id": str(uuid.uuid4()),
                "name": "Cluster A",
                "location": "Gedung DTEDI - Lantai 1",
                "description": "Cluster Laboratorium Telekomunikasi & Jaringan Dasar",
                "room_name": "Lab Telekomunikasi 101",
                "room_id": "ROOM-CLUST-A-101",
                "devices": [
                    {"dev_id": "TS-CLUST-A01", "dev_name": "Sensor Suhu Lab A1", "dev_type": "TS", "marker_x": 35.0, "marker_y": 40.0},
                    {"dev_id": "AC-CLUST-A02", "dev_name": "AC Inverter Lab A1", "dev_type": "AC", "marker_x": 65.0, "marker_y": 40.0},
                ],
                "admin": {
                    "username": "admin_a",
                    "display_name": "Admin Cluster A",
                    "password": "admina123",
                }
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Cluster B",
                "location": "Gedung DTEDI - Lantai 2",
                "description": "Cluster Data Center & Server Komputasi",
                "room_name": "Data Center 201",
                "room_id": "ROOM-CLUST-B-201",
                "devices": [
                    {"dev_id": "TS-CLUST-B01", "dev_name": "Sensor Suhu Rack Server B2", "dev_type": "TS", "marker_x": 40.0, "marker_y": 50.0},
                    {"dev_id": "AC-CLUST-B02", "dev_name": "Precision AC B2", "dev_type": "AC", "marker_x": 70.0, "marker_y": 50.0},
                ],
                "admin": {
                    "username": "admin_b",
                    "display_name": "Admin Cluster B",
                    "password": "adminb123",
                }
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Cluster C",
                "location": "Gedung DTEDI - Lantai 3",
                "description": "Cluster Otomasi Daya & Sistem ATS Genset",
                "room_name": "Ruang Panel ATS 301",
                "room_id": "ROOM-CLUST-C-301",
                "devices": [
                    {"dev_id": "TS-CLUST-C01", "dev_name": "Sensor Suhu Panel C3", "dev_type": "TS", "marker_x": 30.0, "marker_y": 45.0},
                    {"dev_id": "ATS-CLUST-C02", "dev_name": "ATS Genset Utama C3", "dev_type": "ATS", "marker_x": 75.0, "marker_y": 45.0},
                ],
                "admin": {
                    "username": "admin_c",
                    "display_name": "Admin Cluster C",
                    "password": "adminc123",
                }
            },
        ]

        # Get root user ID as creator
        root_user = db.query(User).filter_by(username="root").first()
        root_id = root_user.id if root_user else None

        for item in clusters_info:
            # A. Cluster
            cluster = db.query(Cluster).filter_by(name=item["name"]).first()
            if not cluster:
                cluster = Cluster(
                    id=item["id"],
                    name=item["name"],
                    location=item["location"],
                    description=item["description"],
                    is_active=True,
                    created_by=root_id,
                    created_at=now,
                )
                db.add(cluster)
                db.flush()
                print(f"[CREATED] Cluster: {cluster.name} (ID: {cluster.id})")
            else:
                print(f"[EXISTS]  Cluster: {cluster.name} (ID: {cluster.id})")

            # B. Default Permissions for cluster
            for role_name, perms in DEFAULT_PERMISSIONS.items():
                for perm_key, granted in perms.items():
                    existing_perm = db.query(ClusterRolePermission).filter_by(
                        cluster_id=cluster.id,
                        role=role_name,
                        permission=perm_key
                    ).first()
                    if not existing_perm:
                        db.add(ClusterRolePermission(
                            id=str(uuid.uuid4()),
                            cluster_id=cluster.id,
                            role=role_name,
                            permission=perm_key,
                            granted=granted,
                        ))

            # C. Admin User
            admin_data = item["admin"]
            user = db.query(User).filter_by(username=admin_data["username"]).first()
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    username=admin_data["username"],
                    display_name=admin_data["display_name"],
                    password_hash=hash_password(admin_data["password"]),
                    role="admin",  # Displayed as admin
                    is_active=True,
                    must_change_password=False,
                    created_by=root_id,
                    created_at=now,
                )
                db.add(user)
                db.flush()
                print(f"[CREATED] User: {user.username} ({user.display_name})")
            else:
                # Ensure password and active
                user.password_hash = hash_password(admin_data["password"])
                user.role = "admin"
                user.is_active = True
                user.must_change_password = False
                db.flush()
                print(f"[UPDATED] User: {user.username} ({user.display_name})")

            # D. UserClusterMembership
            membership = db.query(UserClusterMembership).filter_by(
                user_id=user.id,
                cluster_id=cluster.id
            ).first()
            if not membership:
                membership = UserClusterMembership(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    cluster_id=cluster.id,
                    role="admin",
                    created_by=root_id,
                    created_at=now,
                )
                db.add(membership)
                print(f"[ASSIGNED] User {user.username} assigned as admin to {cluster.name}")

            # E. Room
            room = db.query(rooms).filter_by(name=item["room_name"]).first()
            if not room:
                room = rooms(
                    id=item["room_id"],
                    name=item["room_name"],
                    hub_id=hub.hub_id,
                    cluster_id=cluster.id,
                    created_at=now,
                )
                db.add(room)
                db.flush()
                print(f"[CREATED] Room: {room.name} in {cluster.name}")
            else:
                room.cluster_id = cluster.id
                db.flush()

            # F. Devices
            for dev_info in item["devices"]:
                dev = db.query(dev_table).filter_by(dev_id=dev_info["dev_id"]).first()
                if not dev:
                    dev = dev_table(
                        dev_id=dev_info["dev_id"],
                        dev_name=dev_info["dev_name"],
                        dev_type=dev_info["dev_type"],
                        hub_id=hub.hub_id,
                        room_id=room.id,
                        cluster_id=cluster.id,
                        is_active=True,
                        last_status="online",
                        last_seen=now,
                        marker_x=dev_info["marker_x"],
                        marker_y=dev_info["marker_y"],
                        created_at=now,
                    )
                    db.add(dev)
                    db.flush()
                    print(f"[CREATED] Device: {dev.dev_name} ({dev.dev_id}) in {cluster.name}")
                else:
                    dev.cluster_id = cluster.id
                    dev.room_id = room.id
                    dev.is_active = True
                    dev.last_status = "online"
                    dev.last_seen = now
                    db.flush()

                # G. Sample Telemetry Data
                if dev_info["dev_type"] == "TS":
                    temp_row = temperature_data(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        temp=24.2,
                        humid=58.0,
                        timestamp=now,
                    )
                    db.add(temp_row)
                    data_row = data_table(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        dev_name=dev.dev_name,
                        payload={"temp": 24.2, "hum": 58.0, "rssi": -62},
                        timestamp=now,
                    )
                    db.add(data_row)
                elif dev_info["dev_type"] == "AC":
                    temp_row = temperature_data(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        temp=23.8,
                        humid=55.0,
                        timestamp=now,
                    )
                    db.add(temp_row)
                    data_row = data_table(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        dev_name=dev.dev_name,
                        payload={"temp": 23.8, "hum": 55.0, "ac1_pwr": 1, "ac2_pwr": 1, "ac1_temp": 22, "ac2_temp": 22},
                        timestamp=now,
                    )
                    db.add(data_row)
                elif dev_info["dev_type"] == "ATS":
                    ats_row = ats_data(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        pln=224.5,
                        genset=0.0,
                        aki=12.8,
                        state="PLN_ON",
                        rem_hour=0.0,
                        rem_min=0.0,
                        rem_sec=0.0,
                        auto_mode=True,
                        emergency=False,
                        timestamp=now,
                    )
                    db.add(ats_row)
                    data_row = data_table(
                        data_id=str(uuid.uuid4()),
                        dev_id=dev.dev_id,
                        dev_name=dev.dev_name,
                        payload={"v_pln": 224.5, "v_genset": 0.0, "v_batt": 12.8, "mode": "AUTO", "status": "PLN_ON"},
                        timestamp=now,
                    )
                    db.add(data_row)

        db.commit()
        print("\nAll 3 clusters, admins, rooms, devices, and permissions successfully seeded!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_clusters_and_admins()
