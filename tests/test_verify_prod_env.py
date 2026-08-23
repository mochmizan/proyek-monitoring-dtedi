"""
tests/test_verify_prod_env.py - Tests for tools/verify_prod_env.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from tools.verify_prod_env import (
    parse_env_file,
    verify_server_env,
    verify_hub_env,
    VerificationReport,
    check_is_banned,
    mask_secret,
)


def test_mask_secret():
    assert mask_secret("") == "<EMPTY>"
    assert mask_secret("short") == "***"
    assert mask_secret("abcdef123456789") == "abc...789"


def test_banned_values():
    assert check_is_banned("password") is not None
    assert check_is_banned("admin") is not None
    assert check_is_banned("strong_local_hub_key_1234567890abcdef") is not None
    assert check_is_banned("some_CHANGEME_key") is not None
    assert check_is_banned("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") is None


def test_parse_env_file():
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("""
# This is a comment
KEY1=value1
KEY2="quoted value"
KEY3='single quoted'

KEY4=
""")
        temp_path = f.name

    try:
        parsed = parse_env_file(temp_path)
        assert parsed["KEY1"] == "value1"
        assert parsed["KEY2"] == "quoted value"
        assert parsed["KEY3"] == "single quoted"
        assert parsed["KEY4"] == ""
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_verify_server_env_valid():
    report = VerificationReport(mode="prod")
    valid_env = {
        "DATABASE_URL": "postgresql://smsb_admin:StrongSecretPass987%21@db.internal:5432/smsb_prod",
        "HUB_KEY": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
        "CORS_ALLOWED_ORIGINS": "https://smsb.internal",
    }
    verify_server_env(valid_env, report, mode="prod")
    assert not report.has_failures
    assert report.pass_count >= 2


def test_verify_server_env_weak_defaults():
    report = VerificationReport(mode="prod")
    weak_env = {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/database",
        "HUB_KEY": "strong_local_hub_key_1234567890abcdef",
        "CORS_ALLOWED_ORIGINS": "*",
    }
    verify_server_env(weak_env, report, mode="prod", allow_localhost=False)
    assert report.has_failures
    assert report.failure_count >= 2


def test_verify_hub_env_valid():
    report = VerificationReport(mode="prod")
    valid_env = {
        "MQTT_HOST": "localhost",
        "MQTT_PORT": "1883",
        "MQTT_TOPIC": "hs109rs/#",
        "MQTT_USER": "hubadmin",
        "MQTT_PASS": "SuperStrongMqttPassword2026!#",
        "HUB_NAME": "hs109rs-hub-01",
        "HUB_KEY": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0",
        "SERVER_URL": "https://smsb.example.org/api/iot",
        "SERVER_DEVICES_URL": "https://smsb.example.org/api/devices",
        "SERVER_ALERT_URL": "https://smsb.example.org/api/iot/unapproved",
    }
    verify_hub_env(valid_env, report, mode="prod")
    assert not report.has_failures


def test_verify_hub_env_insecure_defaults():
    report = VerificationReport(mode="prod")
    insecure_env = {
        "MQTT_HOST": "localhost",
        "MQTT_PORT": "not_a_number",
        "MQTT_TOPIC": "",
        "MQTT_USER": "",
        "MQTT_PASS": "414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1",
        "HUB_NAME": "",
        "HUB_KEY": "70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4",
        "SERVER_URL": "http://localhost:8000/api/iot",
        "SERVER_DEVICES_URL": "http://localhost:8000/api/devices",
        "SERVER_ALERT_URL": "http://localhost:8000/api/iot/unapproved",
    }
    verify_hub_env(insecure_env, report, mode="prod", allow_localhost=False)
    assert report.has_failures
    assert report.failure_count >= 5
