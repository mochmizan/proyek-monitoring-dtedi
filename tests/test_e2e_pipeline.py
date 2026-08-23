# test_e2e_pipeline.py
# Automated End-to-End Pipeline Integration Tests for Milestone 8 (Tasks 8.1 - 8.5)
# Tests Mock Publisher -> HubBrain Edge Gateway -> HubGate API Server -> PostgreSQL/SQLite Database

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

# Ensure SERVERv5, HUBV5, and tools are on python path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
server_v5_path = os.path.join(repo_root, "SERVERv5", "v5")
hub_v5_path = os.path.join(repo_root, "HUBV5", "V5")
tools_path = os.path.join(repo_root, "tools")

for p in (server_v5_path, hub_v5_path, tools_path):
    if p not in sys.path:
        sys.path.insert(0, p)

# Set test environment variables
TEST_DB_FILE = os.path.join(repo_root, "test_hubgatev5.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"
os.environ["MQTT_PASS"] = "strong_test_mqtt_pass_1234567890abcdef"
os.environ["HUB_KEY"] = "strong_test_hub_key_1234567890abcdef"
os.environ["HUB_ID"] = "hs109rs-hub-01"
os.environ["MQTT_HOST"] = "localhost"
os.environ["MQTT_PORT"] = "1883"

# Initialize backend database & models
import init_sqlv5
init_sqlv5.init_db()

from databasev5 import SessionLocal
from modelsv5 import (
    User, UserSession, hub_table, dev_table, rooms,
    device_threshold_config, temperature_data, ats_data, data_table,
    event_log, pending_commands
)
from auth import hash_password
from hubgatev5 import api
from schemasv5 import IotPayload, TSData, ATSData, ACData
import main as hub_brain
from mock_publishers import build_ts_payload, build_ats_payload, build_ac_payload

client = TestClient(api)
api.state.limiter.enabled = False

HUB_TEST_ID = "hs109rs-hub-01"
HUB_TEST_KEY = "strong_test_hub_key_1234567890abcdef"
TS_DEV_ID = "AA:BB:CC:DD:EE:01"
ATS_DEV_ID = "AA:BB:CC:DD:EE:02"
AC_DEV_ID = "AA:BB:CC:DD:EE:03"


@pytest.fixture(autouse=True)
def setup_test_db():
    db = SessionLocal()
    try:
        # Clean test tables
        db.query(pending_commands).delete()
        db.query(event_log).delete()
        db.query(device_threshold_config).delete()
        db.query(temperature_data).delete()
        db.query(ats_data).delete()
        db.query(data_table).delete()
        db.query(dev_table).delete()
        db.query(rooms).delete()
        db.query(hub_table).delete()
        db.query(UserSession).delete()
        db.query(User).delete()
        db.commit()

        # Seed test admin user
        admin = User(
            id="user-admin-e2e",
            username="admin_e2e",
            password_hash=hash_password("adminpassword123"),
            display_name="Admin E2E",
            role="admin"
        )
        db.add(admin)

        # Seed test Hub
        test_hub = hub_table(
            hub_id=HUB_TEST_ID,
            hub_name="HS109RS Edge Hub",
            hub_key=HUB_TEST_KEY,
            is_active=True
        )
        db.add(test_hub)

        # Seed test Room
        test_room = rooms(
            id="room-server-room-1",
            name="Main Server Room",
            hub_id=HUB_TEST_ID
        )
        db.add(test_room)

        # Seed test Devices
        ts_dev = dev_table(
            dev_id=TS_DEV_ID,
            dev_name="hs109-ts-01",
            dev_type="TS",
            hub_id=HUB_TEST_ID,
            room_id="room-server-room-1",
            is_active=True
        )
        ats_dev = dev_table(
            dev_id=ATS_DEV_ID,
            dev_name="hs109-ats-01",
            dev_type="ATS",
            hub_id=HUB_TEST_ID,
            room_id="room-server-room-1",
            is_active=True
        )
        ac_dev = dev_table(
            dev_id=AC_DEV_ID,
            dev_name="hs109-ac-01",
            dev_type="AC",
            hub_id=HUB_TEST_ID,
            room_id="room-server-room-1",
            is_active=True
        )
        db.add_all([ts_dev, ats_dev, ac_dev])

        # Seed Threshold Config for TS device
        ts_thresh = device_threshold_config(
            dev_id=TS_DEV_ID,
            warning=28.0,
            critical=32.0,
            hysteresis=0.5,
            debounce_seconds=60
        )
        db.add(ts_thresh)

        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def sync_hub_registry(tmp_path):
    """Sets up HubBrain edge cache db and populates whitelist registry."""
    hub_brain.HUB_ID = HUB_TEST_ID
    hub_brain.HUB_KEY = HUB_TEST_KEY
    edge_db = str(tmp_path / "edge_cache_e2e.db")
    hub_brain.EDGE_CACHE_DB_PATH = edge_db
    hub_brain.DB_PATH = edge_db
    hub_brain.init_db(edge_db)

    with hub_brain.DEVICE_REGISTRY_LOCK:
        hub_brain.WHITELIST_DEVICES.clear()
        hub_brain.DEVICE_REGISTRY.clear()
        for dev_id, dev_type, dev_name in [
            (TS_DEV_ID, "TS", "hs109-ts-01"),
            (ATS_DEV_ID, "ATS", "hs109-ats-01"),
            (AC_DEV_ID, "AC", "hs109-ac-01"),
        ]:
            hub_brain.WHITELIST_DEVICES.add(dev_id)
            hub_brain.DEVICE_REGISTRY[dev_id] = {
                "dev_id": dev_id,
                "dev_name": dev_name,
                "dev_type": dev_type,
                "hub_name": "hs109rs"
            }
    yield


# =====================================================================
# 1. Schema Validation Tests for Mock Publisher Payloads
# =====================================================================

def test_mock_publisher_payload_schemas():
    """Verify that mock publisher generators produce payloads compliant with Pydantic schemas."""
    adapter = TypeAdapter(IotPayload)

    ts_data = build_ts_payload(hub_name=HUB_TEST_ID, temp=25.4, humid=58.2)
    validated_ts = adapter.validate_python(ts_data)
    assert isinstance(validated_ts, TSData)
    assert validated_ts.DEV_TYPE == "TS"
    assert validated_ts.TEMP == 25.4

    ats_data = build_ats_payload(
        hub_name=HUB_TEST_ID,
        state="PLN",
        pln=220.5,
        genset=0.0,
        aki=12.8,
        auto_mode=True
    )
    validated_ats = adapter.validate_python(ats_data)
    assert isinstance(validated_ats, ATSData)
    assert validated_ats.DEV_TYPE == "ATS"
    assert validated_ats.PLN == 220.5
    assert validated_ats.AUTO_MODE is True

    ac_data = build_ac_payload(
        hub_name=HUB_TEST_ID,
        ac1_power="ON",
        ac1_temp=24.0,
        ac2_power="OFF",
        ac2_temp=24.0,
        temp=24.5,
        humid=55.0
    )
    validated_ac = adapter.validate_python(ac_data)
    assert isinstance(validated_ac, ACData)
    assert validated_ac.DEV_TYPE == "AC"
    assert validated_ac.AC1_POWER == "ON"


# =====================================================================
# 2. End-to-End Pipeline: Mock ATS Publish -> HubBrain -> HubGate -> DB (Task 8.5)
# =====================================================================

def test_e2e_mock_ats_pipeline_to_database():
    """
    Task 8.5: Verify full pipeline:
    Mock ATS publish -> HubBrain on_message -> HubGate /api/iot -> ats_data row appears in DB.
    """
    ats_payload = build_ats_payload(
        hub_name=HUB_TEST_ID,
        dev_id=ATS_DEV_ID,
        dev_name="hs109-ats-01",
        state="PLN",
        pln=221.8,
        genset=0.0,
        aki=13.1,
        auto_mode=True,
        emergency=False
    )

    # Mock MQTT message wrapper
    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ats/data"
    mock_msg.payload = json.dumps(ats_payload).encode("utf-8")

    # Bridge HubBrain HTTP requests directly to FastAPI TestClient
    def mock_requests_post(url, **kwargs):
        json_data = kwargs.get("json")
        headers = kwargs.get("headers", {})
        resp = client.post("/api/iot", json=json_data, headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        mock_resp.text = resp.text
        mock_resp.json.return_value = resp.json()
        return mock_resp

    with patch("requests.post", side_effect=mock_requests_post):
        # Trigger HubBrain edge message handler
        hub_brain.on_message(None, None, mock_msg)

    # Verify that ats_data row exists in database
    db = SessionLocal()
    try:
        latest_ats = (
            db.query(ats_data)
            .filter(ats_data.dev_id == ATS_DEV_ID)
            .order_by(ats_data.timestamp.desc())
            .first()
        )
        assert latest_ats is not None, "ats_data row was not created in database"
        assert latest_ats.state == "PLN"
        assert abs(latest_ats.pln - 221.8) < 0.01
        assert latest_ats.genset == 0.0
        assert abs(latest_ats.aki - 13.1) < 0.01
        assert latest_ats.auto_mode is True
        assert latest_ats.emergency is False
    finally:
        db.close()


# =====================================================================
# 3. End-to-End Pipeline: Mock TS Publish -> Threshold Evaluation -> Alert
# =====================================================================

def test_e2e_mock_ts_pipeline_to_database_and_alert():
    """
    Verify full TS pipeline:
    Mock TS publish (high temp) -> HubBrain -> HubGate /api/iot -> temperature_data row + event_log Alert.
    """
    ts_payload = build_ts_payload(
        hub_name=HUB_TEST_ID,
        dev_id=TS_DEV_ID,
        dev_name="hs109-ts-01",
        temp=33.5,  # Exceeds critical threshold 32.0
        humid=62.0
    )

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ts/data"
    mock_msg.payload = json.dumps(ts_payload).encode("utf-8")

    def mock_requests_post(url, **kwargs):
        json_data = kwargs.get("json")
        headers = kwargs.get("headers", {})
        resp = client.post("/api/iot", json=json_data, headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        mock_resp.text = resp.text
        mock_resp.json.return_value = resp.json()
        return mock_resp

    with patch("requests.post", side_effect=mock_requests_post):
        hub_brain.on_message(None, None, mock_msg)

    # Verify temperature_data persisted
    db = SessionLocal()
    try:
        latest_temp = (
            db.query(temperature_data)
            .filter(temperature_data.dev_id == TS_DEV_ID)
            .order_by(temperature_data.timestamp.desc())
            .first()
        )
        assert latest_temp is not None
        assert abs(latest_temp.temp - 33.5) < 0.01
        assert abs(latest_temp.humid - 62.0) < 0.01

        # Verify Alert created in event_log
        alert = (
            db.query(event_log)
            .filter(event_log.dev_id == TS_DEV_ID, event_log.metric == "temperature")
            .order_by(event_log.timestamp.desc())
            .first()
        )
        assert alert is not None
        assert alert.severity.lower() == "critical"
        assert abs(alert.value - 33.5) < 0.01
        assert alert.resolved_at is None
    finally:
        db.close()


# =====================================================================
# 4. End-to-End Pipeline: Mock AC Publish -> HubGate Persistence
# =====================================================================

def test_e2e_mock_ac_pipeline_to_database():
    """Verify AC telemetry ingestion through HubBrain to HubGate."""
    ac_payload = build_ac_payload(
        hub_name=HUB_TEST_ID,
        dev_id=AC_DEV_ID,
        dev_name="hs109-ac-01",
        ac1_power="ON",
        ac1_temp=22.0,
        ac2_power="OFF",
        ac2_temp=25.0,
        temp=23.8,
        humid=54.5
    )

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ac/data"
    mock_msg.payload = json.dumps(ac_payload).encode("utf-8")

    def mock_requests_post(url, **kwargs):
        json_data = kwargs.get("json")
        headers = kwargs.get("headers", {})
        resp = client.post("/api/iot", json=json_data, headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        mock_resp.text = resp.text
        return mock_resp

    with patch("requests.post", side_effect=mock_requests_post):
        hub_brain.on_message(None, None, mock_msg)

    db = SessionLocal()
    try:
        latest_data = (
            db.query(data_table)
            .filter(data_table.dev_id == AC_DEV_ID)
            .order_by(data_table.timestamp.desc())
            .first()
        )
        assert latest_data is not None
        assert latest_data.payload["AC1_POWER"] == "ON"
        assert latest_data.payload["AC1_TEMP"] == 22.0
    finally:
        db.close()


# =====================================================================
# 5. End-to-End Downlink Command Dispatch & Mock Node Receipt
# =====================================================================

def test_e2e_downlink_command_dispatch_and_delivery():
    """
    Verify command pipeline:
    Admin creates ATS command -> HubBrain poll_commands_batch -> dispatches to MQTT topic -> ACKs delivery.
    """
    # 1. Login as Admin
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "admin_e2e", "password": "adminpassword123"}
    )
    assert login_resp.status_code == 200
    admin_cookies = {"session_id": login_resp.cookies["session_id"]}

    # 2. Admin submits an ATS command
    cmd_resp = client.post(
        f"/api/devices/{ATS_DEV_ID}/command",
        json={"mode": "manual"},
        cookies=admin_cookies
    )
    assert cmd_resp.status_code in (200, 202)
    cmd_data = cmd_resp.json()
    command_id = cmd_data.get("command_id")
    assert command_id is not None

    # 3. Simulate HubBrain polling commands from HubGate
    mock_mqtt_client = MagicMock()
    mock_publish_result = MagicMock()
    mock_publish_result.is_published.return_value = True
    mock_mqtt_client.publish.return_value = mock_publish_result

    def mock_requests_get(url, **kwargs):
        headers = kwargs.get("headers", {})
        resp = client.get("/api/hub/commands", headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        mock_resp.json.return_value = resp.json()
        return mock_resp

    def mock_requests_post(url, **kwargs):
        # Extract command_id from URL
        cid = url.split("/hub/commands/")[1].split("/delivered")[0]
        headers = kwargs.get("headers", {})
        resp = client.post(f"/api/hub/commands/{cid}/delivered", headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        return mock_resp

    with patch("requests.get", side_effect=mock_requests_get), \
         patch("requests.post", side_effect=mock_requests_post):
        delivered_count = hub_brain.poll_commands_batch(mock_mqtt_client, commands_url="http://testserver/api/hub/commands")

    assert delivered_count >= 1
    # Verify MQTT publish was called on hs109rs/ats/command
    mock_mqtt_client.publish.assert_called()
    called_topic = mock_mqtt_client.publish.call_args[0][0]
    assert called_topic == "hs109rs/ats/command"

    # Verify in DB that command status is DELIVERED
    db = SessionLocal()
    try:
        cmd_record = db.query(pending_commands).filter(pending_commands.command_id == command_id).first()
        assert cmd_record is not None
        assert cmd_record.status == "delivered"
    finally:
        db.close()


# =====================================================================
# 6. End-to-End Edge Cache Backlog Replay Pipeline
# =====================================================================

def test_e2e_edge_cache_offline_replay_pipeline():
    """
    Verify edge offline buffering and recovery:
    HubGate offline -> HubBrain enqueues to SQLite cache -> HubGate back online -> Replay persists to DB.
    """
    offline_payload = build_ats_payload(
        hub_name=HUB_TEST_ID,
        dev_id=ATS_DEV_ID,
        dev_name="hs109-ats-01",
        state="GENSET",
        pln=0.0,
        genset=220.0,
        aki=12.9,
        auto_mode=False
    )

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ats/data"
    mock_msg.payload = json.dumps(offline_payload).encode("utf-8")

    # Step 1: Simulate network outage (HTTP 503 error)
    def mock_failing_post(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        return mock_resp

    with patch("requests.post", side_effect=mock_failing_post):
        hub_brain.on_message(None, None, mock_msg)

    # Verify record is in local SQLite cache
    with hub_brain.create_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_telemetry;")
        cache_count = cursor.fetchone()[0]
        assert cache_count >= 1

    # Step 2: HubGate back online -> replay backlog
    def mock_healthy_post(url, **kwargs):
        json_data = kwargs.get("json")
        headers = kwargs.get("headers", {})
        resp = client.post("/api/iot", json=json_data, headers=headers)
        mock_resp = MagicMock()
        mock_resp.status_code = resp.status_code
        mock_resp.text = resp.text
        return mock_resp

    with patch("requests.post", side_effect=mock_healthy_post):
        replayed = hub_brain.replay_backlog_batch(pacing_delay=0.0)

    assert replayed >= 1

    # Verify SQLite cache is cleared
    with hub_brain.create_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_telemetry;")
        cache_count_after = cursor.fetchone()[0]
        assert cache_count_after == 0

    # Verify database has the replayed GENSET record
    db = SessionLocal()
    try:
        replayed_ats = (
            db.query(ats_data)
            .filter(ats_data.dev_id == ATS_DEV_ID, ats_data.state == "GENSET")
            .order_by(ats_data.timestamp.desc())
            .first()
        )
        assert replayed_ats is not None
        assert abs(replayed_ats.genset - 220.0) < 0.01
        assert replayed_ats.auto_mode is False
    finally:
        db.close()
