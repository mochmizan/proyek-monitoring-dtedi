import os
import subprocess
import sys

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from app.core.csrf import (
    create_csrf_token,
    require_csrf,
    validate_csrf_request,
    validate_login_request,
)
from app.main import api


def make_request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": raw_headers,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
        }
    )


def test_csrf_token_is_bound_to_session():
    token = create_csrf_token("session-a")
    request = make_request(
        "POST",
        "/api/rooms",
        headers={"cookie": "session_id=session-b", "x-csrf-token": token},
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_csrf_request(request)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CSRF_TOKEN_INVALID"


def test_missing_token_has_machine_readable_error_code():
    request = make_request(
        "POST",
        "/api/rooms",
        headers={"cookie": "session_id=session-a"},
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_csrf_request(request)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CSRF_TOKEN_MISSING"


def test_safe_method_and_hub_request_do_not_require_csrf():
    validate_csrf_request(
        make_request("GET", "/api/admin/users", headers={"cookie": "session_id=session-a"})
    )
    validate_csrf_request(
        make_request("POST", "/api/iot", headers={"x-hub-id": "hub", "x-hub-key": "key"})
    )


def test_login_requires_json_and_rejects_unknown_browser_origin():
    with pytest.raises(HTTPException) as content_type_error:
        validate_login_request(make_request("POST", "/api/auth/login"))
    assert content_type_error.value.status_code == 415

    request = make_request(
        "POST",
        "/api/auth/login",
        headers={"content-type": "application/json", "origin": "https://attacker.example"},
    )
    with pytest.raises(HTTPException) as origin_error:
        validate_login_request(request)
    assert origin_error.value.status_code == 403
    assert origin_error.value.detail["code"] == "LOGIN_ORIGIN_INVALID"


def test_cookie_mutations_have_csrf_dependencies_and_hub_routes_do_not():
    login_route = ("POST", "/api/auth/login")
    cookie_routes = {
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/change-password"),
        ("POST", "/api/admin/hubs"),
        ("POST", "/api/hubs/{hub_id}/approve"),
        ("POST", "/api/hubs/{hub_id}/revoke"),
        ("POST", "/api/gateways/{hub_id}/room"),
        ("DELETE", "/api/hubs/{hub_id}"),
        ("POST", "/api/devices/{dev_id}/approve"),
        ("POST", "/api/devices/{dev_id}/pair"),
        ("POST", "/api/devices/{dev_id}/unpair"),
        ("PUT", "/api/devices/{dev_id}/thresholds"),
        ("POST", "/api/devices/{dev_id}/command"),
        ("POST", "/api/rooms"),
        ("PATCH", "/api/rooms/{room_id}"),
        ("DELETE", "/api/rooms/{room_id}"),
        ("POST", "/api/rooms/{room_id}/floor-plan"),
        ("POST", "/api/schedules"),
        ("PATCH", "/api/schedules/{schedule_id}"),
        ("DELETE", "/api/schedules/{schedule_id}"),
        ("POST", "/api/schedules/{schedule_id}/run-now"),
        ("POST", "/api/admin/users"),
        ("PATCH", "/api/admin/users/{user_id}"),
        ("PATCH", "/api/admin/users/{user_id}/status"),
        ("POST", "/api/admin/users/{user_id}/reset-password"),
        ("POST", "/api/admin/users/{user_id}/revoke-sessions"),
        ("DELETE", "/api/admin/users/{user_id}"),
    }
    hub_routes = {
        ("POST", "/api/hubs/pair"),
        ("POST", "/api/iot/unapproved"),
        ("POST", "/api/iot"),
        ("POST", "/api/iot/batch"),
        ("POST", "/api/hub/commands/{command_id}/delivered"),
    }

    found_cookie_routes = set()
    found_hub_routes = set()
    found_unsafe_routes = set()
    for route in api.routes:
        if not isinstance(route, APIRoute):
            continue
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        for method in route.methods:
            key = (method, route.path)
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                found_unsafe_routes.add(key)
            if key in cookie_routes:
                found_cookie_routes.add(key)
                assert dependency_calls & {validate_csrf_request, require_csrf}
            if key in hub_routes:
                found_hub_routes.add(key)
                assert validate_csrf_request not in dependency_calls
                assert require_csrf not in dependency_calls

    assert found_cookie_routes == cookie_routes
    assert found_hub_routes == hub_routes
    assert found_unsafe_routes == cookie_routes | hub_routes | {login_route}


def test_config_rejects_missing_csrf_secret():
    env = os.environ.copy()
    env["CSRF_SECRET"] = " "
    result = subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        cwd=os.path.dirname(__file__),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "CSRF_SECRET must contain at least 32 bytes" in result.stderr
