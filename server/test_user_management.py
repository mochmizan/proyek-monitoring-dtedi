import pytest
from fastapi.testclient import TestClient
from app.main import api

client = TestClient(api)

def test_unauthorized_access_to_admin_users():
    # Tanpa login/session cookie, endpoint admin wajib mengembalikan 401 Unauthorized
    response = client.get("/api/admin/users")
    assert response.status_code == 401

def test_change_password_without_login():
    response = client.post("/api/auth/change-password", json={
        "old_password": "password123",
        "new_password": "newpassword123"
    })
    assert response.status_code == 401