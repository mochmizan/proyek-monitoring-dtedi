# test_milestone2_3.py
# Comprehensive Integration Tests for Milestone 2 & 3

import os
import sys
import uuid
import logging
import time
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

# Configure environment before importing any code
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"
os.environ["SERVER_USER"] = "testadmin"
os.environ["PASSWORD_USER"] = "testpass"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000,http://example.com"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Clean old database if exists
if os.path.exists("./test_hubgatev5.db"):
    try:
        os.remove("./test_hubgatev5.db")
    except Exception as e:
        logging.warning(f"Could not remove old database: {e}")

# Initialize database schema
import init_sqlv5
init_sqlv5.init_db()

# Now import FastAPI test tools and models
from fastapi.testclient import TestClient
from hubgatev5 import api, get_forwarded_address
from databasev5 import SessionLocal
from modelsv5 import hub_table, dev_table, data_table, temperature_data, ats_data, pending_commands

import pytest

client = TestClient(api)
api.state.limiter.enabled = False

@pytest.fixture(scope="module", autouse=True)
def seed_test_data():
    logging.info("--- Seeding test database ---")
    db = SessionLocal()
    try:
        # Import User and hashing helper locally
        from modelsv5 import User, UserSession, LoginAttempt, data_table, temperature_data, ats_data, pending_commands
        from auth import hash_password

        # Clear existing data for clean module run
        db.query(UserSession).delete()
        db.query(LoginAttempt).delete()
        db.query(pending_commands).delete()
        db.query(data_table).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(dev_table).delete()
        db.query(hub_table).delete()
        db.query(User).delete()
        db.commit()

        # Check if already seeded, if not seed it
        h = hub_table(hub_id="TEST_HUB", hub_name="Test Hub", hub_key="test_key", is_active=True)
        db.add(h)
        
        # Add test user for endpoint authentication
        user = User(
            id="test-admin-id-m23",
            username="testadmin",
            password_hash=hash_password("testpass"),
            display_name="Test Admin",
            role="admin"
        )
        db.add(user)
        
        # Add active devices
        d1 = dev_table(dev_id="MAC_TS_01", dev_name="Temp 1", dev_type="TS", hub_id="TEST_HUB", is_active=True)
        d2 = dev_table(dev_id="MAC_ATS_01", dev_name="ATS 1", dev_type="ATS", hub_id="TEST_HUB", is_active=True)
        d3 = dev_table(dev_id="MAC_OTHER_01", dev_name="Other 1", dev_type="AC", hub_id="TEST_HUB", is_active=True)
        
        db.add_all([d1, d2, d3])
        db.commit()
    finally:
        db.close()

def test_telemetry_routing():
    logging.info("--- Test 1: Telemetry Routing ---")
    
    # 1. TSData -> temperature_data table
    ts_payload = {
        "HUB_NAME": "TEST_HUB",
        "DEV_ID": "MAC_TS_01",
        "DEV_NAME": "Temp 1",
        "DEV_TYPE": "TS",
        "TEMP": 23.5,
        "HUMID": 45.2
    }
    headers = {"X-Hub-ID": "TEST_HUB", "X-Hub-Key": "test_key"}
    response = client.post("/api/iot", json=ts_payload, headers=headers)
    assert response.status_code == 200, f"Failed to post TSData: {response.text}"
    
    # Verify in DB
    db = SessionLocal()
    ts_rows = db.query(temperature_data).filter(temperature_data.dev_id == "MAC_TS_01").all()
    assert len(ts_rows) == 1, "TSData row was not created in temperature_data table!"
    assert ts_rows[0].temp == 23.5
    assert ts_rows[0].humid == 45.2
    
    # 2. ATSData -> ats_data table
    ats_payload = {
        "HUB_NAME": "TEST_HUB",
        "DEV_ID": "MAC_ATS_01",
        "DEV_NAME": "ATS 1",
        "DEV_TYPE": "ATS",
        "STATE": "manual",
        "PLN": 220.0,
        "GENSET": 0.0,
        "AKI": 12.0,
        "REM_HOUR": 1.0,
        "REM_MIN": 2.0,
        "REM_SEC": 3.0,
        "AUTO_MODE": False,
        "EMERGENCY": False
    }
    response = client.post("/api/iot", json=ats_payload, headers=headers)
    assert response.status_code == 200, f"Failed to post ATSData: {response.text}"
    
    # Verify in DB
    ats_rows = db.query(ats_data).filter(ats_data.dev_id == "MAC_ATS_01").all()
    assert len(ats_rows) == 1, "ATSData row was not created in ats_data table!"
    assert ats_rows[0].state == "manual"
    assert ats_rows[0].auto_mode is False

    # 3. Other payload (e.g. AC) -> generic data_table
    ac_payload = {
        "HUB_NAME": "TEST_HUB",
        "DEV_ID": "MAC_OTHER_01",
        "DEV_NAME": "Other 1",
        "DEV_TYPE": "AC",
        "AC1_POWER": "on",
        "AC1_TEMP": 18.0,
        "AC2_POWER": "off",
        "AC2_TEMP": 24.0,
        "TEMP": 22.0,
        "HUMID": 50.0
    }
    response = client.post("/api/iot", json=ac_payload, headers=headers)
    assert response.status_code == 200, f"Failed to post ACData: {response.text}"
    
    # Verify in DB
    generic_rows = db.query(data_table).filter(data_table.dev_id == "MAC_OTHER_01").all()
    assert len(generic_rows) == 1, "ACData row was not created in generic data_table!"
    assert generic_rows[0].payload["DEV_TYPE"] == "AC"
    
    db.close()
    logging.info("Telemetry Routing Tests PASSED!")

def test_command_relay():
    logging.info("--- Test 2: Command Relay Endpoints ---")
    
    # Login to get session cookie
    login_response = client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert login_response.status_code == 200, f"Login failed during test setup: {login_response.text}"
    session_id = login_response.cookies.get("session_id")
    cookies = {"session_id": session_id}
    
    # 1. Post command to non-existent device -> 404
    cmd_payload = {"mode": "manual", "start_genset": "on"}
    response = client.post(
        "/api/devices/MAC_FAKE/command",
        json=cmd_payload,
        cookies=cookies
    )
    assert response.status_code == 404, f"Expected 404 for non-existent device, got {response.status_code}"

    # 2. Post valid command (last known mode is manual for MAC_ATS_01, so start_genset='on' is valid)
    response = client.post(
        "/api/devices/MAC_ATS_01/command",
        json=cmd_payload,
        cookies=cookies
    )
    assert response.status_code == 200, f"Failed to post valid command: {response.text}"
    cmd_data = response.json()
    assert cmd_data["status"] == "queued"
    command_id = cmd_data["command_id"]
    
    # 3. Verify queued command is pending in database
    db = SessionLocal()
    cmd_row = db.get(pending_commands, command_id)
    assert cmd_row is not None
    assert cmd_row.status == "pending"
    db.close()
    
    # 4. Get pending commands from Hub endpoint
    headers = {"X-Hub-ID": "TEST_HUB", "X-Hub-Key": "test_key"}
    response = client.get("/api/hub/commands", headers=headers)
    assert response.status_code == 200, f"Failed to get hub commands: {response.text}"
    cmds_list = response.json()
    assert len(cmds_list) == 1
    assert cmds_list[0]["command_id"] == command_id
    assert cmds_list[0]["payload"]["start_genset"] == "on"

    # 5. Mark command as delivered
    response = client.post(f"/api/hub/commands/{command_id}/delivered", headers=headers)
    assert response.status_code == 200, f"Failed to mark delivered: {response.text}"
    
    # 6. Verify in DB
    db = SessionLocal()
    cmd_row = db.get(pending_commands, command_id)
    assert cmd_row.status == "delivered"
    assert cmd_row.delivered_at is not None
    db.close()
    
    # 7. Get pending commands again -> should be empty
    response = client.get("/api/hub/commands", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 0

    # 8. Post command to start genset when last known mode is auto
    # Let's post telemetry setting mode to auto (auto_mode = True)
    ats_payload_auto = {
        "HUB_NAME": "TEST_HUB",
        "DEV_ID": "MAC_ATS_01",
        "DEV_NAME": "ATS 1",
        "DEV_TYPE": "ATS",
        "STATE": "auto",
        "PLN": 220.0,
        "GENSET": 0.0,
        "AKI": 12.0,
        "REM_HOUR": 1.0,
        "REM_MIN": 2.0,
        "REM_SEC": 3.0,
        "AUTO_MODE": True,
        "EMERGENCY": False
    }
    headers = {"X-Hub-ID": "TEST_HUB", "X-Hub-Key": "test_key"}
    response = client.post("/api/iot", json=ats_payload_auto, headers=headers)
    assert response.status_code == 200
    
    # Now try to command start_genset = 'on'. Pydantic validation should fail context check and return 422.
    response = client.post(
        "/api/devices/MAC_ATS_01/command",
        json={"start_genset": "on"},
        cookies=cookies
    )
    assert response.status_code == 422, f"Expected 422 since last known mode was auto, got {response.status_code}: {response.text}"
    
    logging.info("Command Relay Endpoints Tests PASSED!")

def test_cors_middleware():
    logging.info("--- Test 3: CORS Middleware ---")
    headers = {"Origin": "http://example.com"}
    response = client.get("/api/devices", headers=headers)
    assert response.headers.get("access-control-allow-origin") == "http://example.com"
    
    headers_bad = {"Origin": "http://badorigin.com"}
    response_bad = client.get("/api/devices", headers=headers_bad)
    assert response_bad.headers.get("access-control-allow-origin") is None
    logging.info("CORS Middleware Tests PASSED!")

def test_ip_resolver():
    logging.info("--- Test 4: X-Forwarded-For & X-Real-IP Resolver ---")
    # 1. Test X-Real-IP is checked first
    mock_req_real = MagicMock()
    mock_req_real.headers = {"X-Real-IP": "198.51.100.42", "X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
    resolved_ip_real = get_forwarded_address(mock_req_real)
    assert resolved_ip_real == "198.51.100.42"

    # 2. Test X-Forwarded-For returns the first IP in the chain (original client)
    mock_req = MagicMock()
    mock_req.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
    resolved_ip = get_forwarded_address(mock_req)
    assert resolved_ip == "203.0.113.195"
    
    # 3. Test fallback to get_remote_address
    mock_req_no_header = MagicMock()
    mock_req_no_header.headers = {}
    mock_req_no_header.client.host = "127.0.0.1"
    resolved_ip_fallback = get_forwarded_address(mock_req_no_header)
    assert resolved_ip_fallback == "127.0.0.1"
    logging.info("X-Forwarded-For & X-Real-IP Resolver Tests PASSED!")

def test_edge_daemon_polling():
    logging.info("--- Test 5: Edge Daemon main.py (Headless Polling Loop) ---")
    
    # Add sys.path of hub
    hub_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "hub"))
    if hub_path not in sys.path:
        sys.path.insert(0, hub_path)
        
    # We patch env before importing/running the edge daemon to avoid weak keys exception
    with patch.dict(os.environ, {
        "MQTT_PASS": "strong_pass_123456_strong_pass_123456",
        "HUB_KEY": "strong_key_123456_strong_key_123456",
        "MQTT_HOST": "localhost",
        "MQTT_PORT": "1883",
        "SERVER_DEVICES_URL": "http://localhost:8000/api/devices"
    }):
        # Mock requests and mqtt client inside main
        import main
        
        # Test startup fails on weak key
        with patch.dict(os.environ, {"HUB_KEY": main.WEAK_HUB_KEY}):
            try:
                import importlib
                importlib.reload(main)
                assert False, "Should fail with weak key"
            except RuntimeError as e:
                logging.info(f"Weak key startup check properly raised: {e}")
                
        # Reload main back to a valid configuration
        importlib.reload(main)
        
        # Setup mock client
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.publish.return_value = MagicMock(rc=0) # successful publish
        
        # Mock GET response for commands
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = [
            {
                "command_id": "test-cmd-id-999",
                "dev_id": "MAC_ATS_01",
                "payload": {"mode": "manual", "start_genset": "on"}
            }
        ]
        
        mock_post = MagicMock()
        mock_post.status_code = 200
        
        def mock_requests_get(url, *args, **kwargs):
            if "hub/commands" in url:
                return mock_get
            return MagicMock(status_code=404)
            
        def mock_requests_post(url, *args, **kwargs):
            if "delivered" in url:
                return mock_post
            return MagicMock(status_code=404)
            
        with patch("requests.get", side_effect=mock_requests_get), \
             patch("requests.post", side_effect=mock_requests_post):
             
             # We want to run poll_commands once. We patch time.sleep inside it to raise an exception to exit loop.
             class ExitLoopException(Exception):
                 pass
                 
             with patch("time.sleep", side_effect=ExitLoopException()):
                 try:
                     main.poll_commands(mock_mqtt_client)
                 except ExitLoopException:
                     pass
                     
             # Verify MQTT publish was called
             mock_mqtt_client.publish.assert_called_once_with(
                 "hs109rs/ats/command",
                 '{"mode": "manual", "start_genset": "on"}'
             )
             logging.info("Edge Daemon successfully published command to local MQTT broker!")

    logging.info("Edge Daemon Tests PASSED!")

if __name__ == "__main__":
    try:
        seed_test_data()
        test_telemetry_routing()
        test_command_relay()
        test_cors_middleware()
        test_ip_resolver()
        test_edge_daemon_polling()
        logging.info("=== ALL INTEGRATION TESTS PASSED SUCCESSFULLY! ===")
    finally:
        # Dispose any DB connections to release locks
        from databasev5 import engine as db_engine
        db_engine.dispose()
        
        # Clean up database test file
        if os.path.exists("./test_hubgatev5.db"):
            try:
                os.remove("./test_hubgatev5.db")
                logging.info("Test database cleaned up successfully.")
            except Exception as e:
                logging.warning(f"Could not remove test database at cleanup: {e}")
