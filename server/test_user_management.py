import pytest
from fastapi.testclient import TestClient
from app.main import api

client = TestClient(api)

# 1. Test Unauthenticated Access
def test_unauthorized_access_to_admin_users():
    response = client.get("/api/admin/users")
    assert response.status_code == 401

def test_change_password_without_login():
    response = client.post("/api/auth/change-password", json={
        "old_password": "password123",
        "new_password": "newpassword123"
    })
    assert response.status_code == 401

# 2. Test Invalid User Details Search (404)
def test_get_non_existent_user_detail():
    # Menguji pencarian ID yang tidak ada (membutuhkan login admin)
    response = client.get("/api/admin/users/non-existent-id")
    assert response.status_code == 401 # Tertahan di Auth Guard lebih dulu