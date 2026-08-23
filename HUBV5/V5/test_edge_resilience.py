import os
import sys
import json
import time
import tempfile
import sqlite3
import requests
import pytest
from unittest.mock import MagicMock, patch, call

# Ensure HUBV5/V5 is in sys.path
hub_dir = os.path.dirname(os.path.abspath(__file__))
if hub_dir not in sys.path:
    sys.path.insert(0, hub_dir)

# Set valid environment variables before importing main to satisfy security checks
os.environ["MQTT_PASS"] = "strong_test_mqtt_pass_1234567890abcdef"
os.environ["HUB_KEY"] = "strong_test_hub_key_1234567890abcdef"
os.environ["MQTT_HOST"] = "localhost"
os.environ["MQTT_PORT"] = "1883"
os.environ["HUB_ID"] = "hs109rs-hub-01"

import main


@pytest.fixture
def temp_db(tmp_path):
    """Creates a temporary SQLite database for testing edge caching."""
    db_file = str(tmp_path / "test_edge_cache.db")
    main.EDGE_CACHE_DB_PATH = db_file
    main.DB_PATH = db_file
    main.init_db(db_file)
    yield db_file
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def reset_registry():
    """Resets global in-memory whitelist and device registry between tests."""
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.clear()
        main.DEVICE_REGISTRY.clear()
    yield
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.clear()
        main.DEVICE_REGISTRY.clear()


# =====================================================================
# 1. Tests for SQLite WAL Cache Initialization & PRAGMAs (Task 6.1)
# =====================================================================

def test_db_pragmas_and_schema(temp_db):
    """Verify SQLite WAL mode, PRAGMAs, and schema creation."""
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()

    # Check journal_mode = wal
    cursor.execute("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == "wal"

    # Check busy_timeout = 5000
    cursor.execute("PRAGMA busy_timeout;")
    busy_timeout = cursor.fetchone()[0]
    assert busy_timeout == 5000

    # Check table structure
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_telemetry';")
    assert cursor.fetchone() is not None

    # Check index structure
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pending_created';")
    assert cursor.fetchone() is not None

    conn.close()


# =====================================================================
# 2. Tests for Offline Buffering on Forward Failure (Tasks 6.1, 6.2, 11.4)
# =====================================================================

def test_offline_buffering_on_network_failure(temp_db):
    """When direct HTTPS POST fails due to network error, telemetry is buffered into SQLite."""
    dev_id = "A4:CF:12:F1:C0:01"
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.add(dev_id)

    payload_data = {
        "DEV_ID": dev_id,
        "DEV_NAME": "hs109-ts-01",
        "temperature": 25.4,
        "humidity": 60.2
    }

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ts/telemetry"
    mock_msg.payload = json.dumps(payload_data).encode("utf-8")
    mock_client = MagicMock()

    # Simulate network connection failure
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Network unreachable")):
        main.on_message(mock_client, None, mock_msg)

    # Verify record was stored in SQLite
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, payload, created_at FROM pending_telemetry")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == 1
    saved_payload = json.loads(rows[0][1])
    assert saved_payload["DEV_ID"] == dev_id
    assert saved_payload["temperature"] == 25.4


def test_offline_buffering_on_http_500_failure(temp_db):
    """When direct HTTPS POST returns HTTP 5xx, telemetry is buffered into SQLite."""
    dev_id = "A4:CF:12:F1:C0:02"
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.add(dev_id)

    payload_data = {
        "DEV_ID": dev_id,
        "DEV_NAME": "hs109-ats-01",
        "v_r": 220.5,
        "mode": "auto"
    }

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ats/telemetry"
    mock_msg.payload = json.dumps(payload_data).encode("utf-8")
    mock_client = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_resp):
        main.on_message(mock_client, None, mock_msg)

    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, payload FROM pending_telemetry")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 1
    assert json.loads(rows[0][1])["DEV_ID"] == dev_id


def test_unregistered_device_dropped_not_buffered(temp_db):
    """Unapproved/unregistered device is dropped and never written to offline cache."""
    dev_id = "UNKNOWN:DEV:99"
    # Not in WHITELIST_DEVICES

    payload_data = {
        "DEV_ID": dev_id,
        "temperature": 99.9
    }

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ts/telemetry"
    mock_msg.payload = json.dumps(payload_data).encode("utf-8")
    mock_client = MagicMock()

    with patch("requests.post") as mock_post:
        main.on_message(mock_client, None, mock_msg)
        for call_args in mock_post.call_args_list:
            assert call_args[0][0] != main.SERVER_URL

    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM pending_telemetry")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 0


# =====================================================================
# 3. Tests for Paced FIFO Replay (Tasks 6.3, 11.4)
# =====================================================================

def test_paced_fifo_replay_success(temp_db):
    """Replay drains pending records in strict FIFO order, deletes on 200/201, and applies pacing."""
    # Seed 3 records into pending_telemetry
    records = [
        {"DEV_ID": "DEV_01", "seq": 1},
        {"DEV_ID": "DEV_02", "seq": 2},
        {"DEV_ID": "DEV_03", "seq": 3}
    ]
    for r in records:
        main.enqueue_pending_telemetry(r, temp_db)

    # Verify 3 records in DB
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM pending_telemetry")
    assert cursor.fetchone()[0] == 3
    conn.close()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    posted_payloads = []
    def record_post(url, json=None, **kwargs):
        posted_payloads.append(json)
        return mock_resp

    with patch("requests.post", side_effect=record_post), \
         patch("time.sleep") as mock_sleep:
        replayed = main.replay_backlog_batch(db_path=temp_db, batch_size=10, pacing_delay=0.35)

    assert replayed == 3
    assert len(posted_payloads) == 3
    # Check strict FIFO ordering (seq 1 -> seq 2 -> seq 3)
    assert posted_payloads[0]["seq"] == 1
    assert posted_payloads[1]["seq"] == 2
    assert posted_payloads[2]["seq"] == 3

    # Check pacing sleep was called between replayed items
    assert mock_sleep.call_count == 3
    mock_sleep.assert_called_with(0.35)

    # Verify cache is now completely empty
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM pending_telemetry")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_replay_rate_limit_429_backoff(temp_db):
    """On HTTP 429 Too Many Requests, replay pauses and does not delete the unacked record."""
    main.enqueue_pending_telemetry({"DEV_ID": "DEV_429_01"}, temp_db)
    main.enqueue_pending_telemetry({"DEV_ID": "DEV_429_02"}, temp_db)

    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.text = "Rate limit exceeded"

    with patch("requests.post", return_value=mock_resp_429), \
         patch("time.sleep") as mock_sleep:
        replayed = main.replay_backlog_batch(db_path=temp_db, batch_size=10, pacing_delay=0.35)

    assert replayed == 0
    # Sleep 15s backoff
    mock_sleep.assert_called_with(15)

    # Both records remain in DB for next retry
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM pending_telemetry")
    assert cursor.fetchone()[0] == 2
    conn.close()


def test_replay_permanent_error_400_quarantine(temp_db):
    """On HTTP 400/403/422 permanent failure, record is discarded to prevent queue blockage."""
    main.enqueue_pending_telemetry({"DEV_ID": "DEV_BAD_SCHEMA"}, temp_db)
    main.enqueue_pending_telemetry({"DEV_ID": "DEV_GOOD"}, temp_db)

    def mock_post(url, json=None, **kwargs):
        if json.get("DEV_ID") == "DEV_BAD_SCHEMA":
            resp = MagicMock()
            resp.status_code = 422
            resp.text = "Unprocessable Entity"
            return resp
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("requests.post", side_effect=mock_post), \
         patch("time.sleep"):
        replayed = main.replay_backlog_batch(db_path=temp_db, batch_size=10, pacing_delay=0.35)

    assert replayed == 1

    # Both records should no longer be in DB (bad one quarantined/deleted, good one successfully replayed)
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM pending_telemetry")
    assert cursor.fetchone()[0] == 0
    conn.close()


# =====================================================================
# 4. Tests for Zero-Backpressure Invariant (Task 6.4)
# =====================================================================

def test_live_forwarding_during_backlog(temp_db):
    """
    Zero-backpressure invariant:
    Incoming live telemetry must be forwarded immediately via HTTPS POST without
    being queued behind existing offline backlog records.
    """
    # 1. Pre-populate database with offline backlog records
    main.enqueue_pending_telemetry({"DEV_ID": "BACKLOG_1", "created_at": 100}, temp_db)
    main.enqueue_pending_telemetry({"DEV_ID": "BACKLOG_2", "created_at": 200}, temp_db)

    live_dev_id = "A4:CF:12:F1:C0:LIVE"
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.add(live_dev_id)

    live_payload = {
        "DEV_ID": live_dev_id,
        "DEV_NAME": "live-sensor",
        "temperature": 23.5
    }

    mock_msg = MagicMock()
    mock_msg.topic = "hs109rs/ts/telemetry"
    mock_msg.payload = json.dumps(live_payload).encode("utf-8")
    mock_client = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    # 2. Receive live message while backlog exists in database
    with patch("requests.post", return_value=mock_resp) as mock_post:
        main.on_message(mock_client, None, mock_msg)

        # Assert direct POST was called immediately for live message
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["json"]["DEV_ID"] == live_dev_id

    # 3. Assert backlog is still intact in SQLite and live message was not added to SQLite
    conn = main.create_db_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, payload FROM pending_telemetry ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2
    assert json.loads(rows[0][1])["DEV_ID"] == "BACKLOG_1"
    assert json.loads(rows[1][1])["DEV_ID"] == "BACKLOG_2"


# =====================================================================
# 5. Tests for Device Registry & Dynamic Command Topic Resolution (Tasks 6.5, 6.6, 11.5)
# =====================================================================

def test_sync_whitelist_and_device_registry():
    """Verify sync_whitelist populates WHITELIST_DEVICES and DEVICE_REGISTRY metadata."""
    mock_devices_response = [
        {"DEV_ID": "A4:CF:12:F1:C0:01", "DEV_NAME": "hs109-ats-01", "DEV_TYPE": "ATS", "HUB_NAME": "hs109rs"},
        {"DEV_ID": "A4:CF:12:F1:C0:02", "DEV_NAME": "hs109-ac-01", "DEV_TYPE": "AC", "HUB_NAME": "hs109rs"},
        {"DEV_ID": "A4:CF:12:F1:C0:03", "DEV_NAME": "hs109-ts-01", "DEV_TYPE": "TS", "HUB_NAME": "hs109rs"}
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_devices_response

    with patch("requests.get", return_value=mock_resp):
        success = main.sync_whitelist_once()
        assert success is True

    with main.DEVICE_REGISTRY_LOCK:
        assert len(main.WHITELIST_DEVICES) == 3
        assert "A4:CF:12:F1:C0:01" in main.WHITELIST_DEVICES
        assert "A4:CF:12:F1:C0:02" in main.WHITELIST_DEVICES
        assert "A4:CF:12:F1:C0:03" in main.WHITELIST_DEVICES

        ats_info = main.DEVICE_REGISTRY.get("A4:CF:12:F1:C0:01")
        assert ats_info["dev_type"] == "ATS"
        assert ats_info["hub_name"] == "hs109rs"

        ac_info = main.DEVICE_REGISTRY.get("A4:CF:12:F1:C0:02")
        assert ac_info["dev_type"] == "AC"


def test_dynamic_topic_resolution_and_dispatch_ats_and_ac():
    """
    Test dynamic downlink topic derivation:
    ATS commands -> {HUB_NAME}/ats/command
    AC commands -> {HUB_NAME}/ac/command
    And delivery acknowledgment via POST /delivered.
    """
    # 1. Setup registry
    with main.DEVICE_REGISTRY_LOCK:
        main.DEVICE_REGISTRY["A4:CF:12:F1:C0:01"] = {
            "dev_id": "A4:CF:12:F1:C0:01",
            "dev_name": "hs109-ats-01",
            "dev_type": "ATS",
            "hub_name": "hs109rs"
        }
        main.DEVICE_REGISTRY["A4:CF:12:F1:C0:02"] = {
            "dev_id": "A4:CF:12:F1:C0:02",
            "dev_name": "hs109-ac-01",
            "dev_type": "AC",
            "hub_name": "hs109rs"
        }

    # 2. Mock pending commands returned from server
    commands_response = [
        {
            "command_id": "cmd-ats-001",
            "dev_id": "A4:CF:12:F1:C0:01",
            "payload": {"mode": "manual", "start_genset": "on"}
        },
        {
            "command_id": "cmd-ac-001",
            "dev_id": "A4:CF:12:F1:C0:02",
            "payload": {"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 24"}
        }
    ]

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = commands_response

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200

    mock_client = MagicMock()
    mock_client.publish.return_value = MagicMock(rc=0, is_published=lambda: True)

    def mock_requests_get(url, *args, **kwargs):
        if "commands" in url:
            return mock_get_resp
        return MagicMock(status_code=404)

    delivered_calls = []
    def mock_requests_post(url, *args, **kwargs):
        if "delivered" in url:
            delivered_calls.append(url)
            return mock_post_resp
        return MagicMock(status_code=404)

    with patch("requests.get", side_effect=mock_requests_get), \
         patch("requests.post", side_effect=mock_requests_post):
        delivered_count = main.poll_commands_batch(mock_client)

    assert delivered_count == 2

    # Verify MQTT publishes to generalized topics
    assert mock_client.publish.call_count == 2
    pub_calls = mock_client.publish.call_args_list

    # ATS call
    assert pub_calls[0][0][0] == "hs109rs/ats/command"
    assert json.loads(pub_calls[0][0][1]) == {"mode": "manual", "start_genset": "on"}

    # AC call
    assert pub_calls[1][0][0] == "hs109rs/ac/command"
    assert json.loads(pub_calls[1][0][1]) == {"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 24"}

    # Verify ACKs were posted for both commands
    assert len(delivered_calls) == 2
    assert "cmd-ats-001/delivered" in delivered_calls[0]
    assert "cmd-ac-001/delivered" in delivered_calls[1]


def test_command_fallback_inference():
    """Verify fallback dev_type inference when device is not yet in DEVICE_REGISTRY."""
    # AC payload inference
    topic_ac = main.derive_command_topic("UNCACHED_DEV_01", {"AC_NUMBER": "AC2", "AC_COMMAND": "ON"})
    assert topic_ac == "hs109rs/ac/command"

    # ATS payload inference
    topic_ats = main.derive_command_topic("UNCACHED_DEV_02", {"mode": "auto"})
    assert topic_ats == "hs109rs/ats/command"


def test_command_payload_validation():
    """Verify payload validator contracts for AC and ATS."""
    # AC Validations
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "ON"})[0] is True
    assert main.validate_ac_payload({"AC_NUMBER": "AC2", "AC_COMMAND": "OFF"})[0] is True
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 16"})[0] is True
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 30"})[0] is True
    assert main.validate_ac_payload({"AC_NUMBER": "AC3", "AC_COMMAND": "ON"})[0] is False
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 15"})[0] is False
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "TEMP 31"})[0] is False
    assert main.validate_ac_payload({"AC_NUMBER": "AC1", "AC_COMMAND": "INVALID"})[0] is False

    # ATS Validations
    assert main.validate_ats_payload({"mode": "auto"})[0] is True
    assert main.validate_ats_payload({"start_genset": "on"})[0] is True
    assert main.validate_ats_payload({"reset": "rst"})[0] is True
    assert main.validate_ats_payload({"invalid_key": 123})[0] is False
