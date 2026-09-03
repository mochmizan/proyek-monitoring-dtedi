# test_hub_delete.py - DELETE /api/hubs/{hub_id}: admin-only hard delete, FK-safe
import os
import sys

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"
os.environ["HUB_BOOTSTRAP_KEY"] = "bootstrap_secret_test"

import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import User, UserSession, LoginAttempt, hub_table, dev_table, rooms
from auth import hash_password
from app.main import api

client = TestClient(api)
api.state.limiter.enabled = False


@pytest.fixture(scope="module", autouse=True)
def setup_env():
    db = SessionLocal()
    try:
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(User).delete()
        db.commit()
        db.add(User(id="u-adm", username="adm", password_hash=hash_password("pw"), display_name="A", role="admin"))
        db.add(User(id="u-op", username="op", password_hash=hash_password("pw"), display_name="O", role="operator"))
        db.add(hub_table(hub_id="HUB_DEL_1", hub_name="Doomed Hub", hub_key="k1", is_active=True))
        db.add(hub_table(hub_id="HUB_DEL_2", hub_name="Device Hub", hub_key="k2", is_active=True))
        db.add(rooms(id="room-del", name="Del Room", hub_id="HUB_DEL_1"))
        db.add(dev_table(dev_id="dev:del:2", dev_name="D", dev_type="TS", hub_id="HUB_DEL_2", is_active=True))
        db.commit()
    finally:
        db.close()
    yield


def _login(username):
    return client.post("/api/auth/login", json={"username": username, "password": "pw"})


def test_delete_hub_admin_clears_room_link():
    token = _login("adm")
    assert token.status_code == 200
    resp = client.delete("/api/hubs/HUB_DEL_1")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deleted"
    db = SessionLocal()
    try:
        assert db.get(hub_table, "HUB_DEL_1") is None
        room = db.get(rooms, "room-del")
        assert room is not None and room.hub_id is None  # room survives, link cleared
    finally:
        db.close()


def test_delete_hub_with_devices_conflict():
    _login("adm")
    resp = client.delete("/api/hubs/HUB_DEL_2")
    assert resp.status_code == 409


def test_delete_hub_missing_404():
    _login("adm")
    assert client.delete("/api/hubs/NOPE").status_code == 404


def test_delete_hub_operator_forbidden():
    _login("op")
    assert client.delete("/api/hubs/HUB_DEL_2").status_code == 403