"""
tests/test_verify_production_deployment.py - Tests for tools/verify_production_deployment.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from tools.verify_production_deployment import ProductionVerifier, StepResult, PipelineReport


def test_verifier_report_properties():
    report = PipelineReport(base_url="https://test.server")
    assert report.passed is True
    assert report.fail_count == 0
    assert report.pass_count == 0

    report.results.append(StepResult(step_num=1, name="Step 1", status="PASS", details="OK"))
    report.results.append(StepResult(step_num=2, name="Step 2", status="SKIP", details="Skipped"))
    assert report.passed is True
    assert report.pass_count == 1

    report.results.append(StepResult(step_num=3, name="Step 3", status="FAIL", details="Error"))
    assert report.passed is False
    assert report.fail_count == 1


def test_verifier_flow_mocked():
    verifier = ProductionVerifier(
        base_url="http://127.0.0.1:8000",
        username="admin",
        password="secretpassword",
        hub_id="hs109rs-hub-01",
        hub_key="test_hub_key_1234567890abcdef1234567890abcdef",
    )

    state = {"logged_in": False, "csrf_token": "verifier-csrf-token"}

    def mock_request(method, endpoint, data=None, headers=None):
        if endpoint == "/api/auth/me":
            if state["logged_in"]:
                return 200, {"username": "admin", "role": "admin", "id": "u1"}, {}
            return 401, {"detail": "Unauthorized"}, {}
        elif endpoint == "/":
            return 200, "<html><head><title>SMSB</title></head><body><div id=\"root\"></div></body></html>", {}
        elif endpoint == "/api/auth/login":
            state["logged_in"] = True
            return 200, {"username": "admin", "role": "admin", "id": "u1"}, {}
        elif endpoint == "/api/auth/csrf-token":
            if state["logged_in"]:
                return 200, {"csrf_token": state["csrf_token"]}, {"cache-control": "no-store"}
            return 401, {"detail": "Unauthorized"}, {}
        elif endpoint == "/api/rooms":
            return 200, [{"id": "r1", "name": "Room 101"}], {}
        elif endpoint == "/api/devices":
            return 200, [{"dev_id": "ts1", "dev_name": "Sensor 1"}], {}
        elif endpoint == "/api/alerts":
            return 200, {"total": 0, "items": []}, {}
        elif endpoint == "/api/iot":
            return 200, {"status": "success"}, {}
        elif endpoint == "/api/auth/logout":
            assert headers == {"X-CSRF-Token": state["csrf_token"]}
            state["logged_in"] = False
            return 200, {"status": "logged out"}, {}
        return 404, {"detail": "Not found"}, {}

    with patch.object(verifier, "_request", side_effect=mock_request):
        report = verifier.run_all_checks()
        assert report.passed is True
        assert report.pass_count >= 6
        assert report.fail_count == 0
