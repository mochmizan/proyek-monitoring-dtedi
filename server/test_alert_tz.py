# test_alert_tz.py - API datetime contract: naive UTC from SQLite must serialize as tz-aware UTC.
# Root cause 2026-08-31: alerts endpoint emitted naive "2026-08-31T05:41:07" (no Z) ->
# browser new Date() parsed it as LOCAL time -> double shift (05:41Z displayed as 05:41 WIB).
from datetime import UTC, datetime

from schemasv5 import AlertResponse, DeviceResponse, HubResponse, TelemetryHistoryPoint


def test_alert_response_naive_timestamp_becomes_utc():
    naive = datetime(2026, 8, 31, 5, 41, 7)  # SQLite-style naive UTC
    alert = AlertResponse(event_id="e1", timestamp=naive)
    assert alert.timestamp.tzinfo is not None, "timestamp must be tz-aware"
    assert alert.timestamp.utcoffset().total_seconds() == 0
    assert alert.timestamp.hour == 5  # UTC wall clock preserved, not shifted


def test_alert_response_naive_resolved_at_becomes_utc():
    alert = AlertResponse(event_id="e1", timestamp=datetime(2026, 8, 31, 5, 0, 0), resolved_at=datetime(2026, 8, 31, 6, 0, 0))
    assert alert.resolved_at is not None and alert.resolved_at.tzinfo is not None


def test_alert_response_aware_timestamp_untouched():
    aware = datetime(2026, 8, 31, 5, 0, 0, tzinfo=UTC)
    alert = AlertResponse(event_id="e1", timestamp=aware)
    assert alert.timestamp == aware


def test_serialized_json_carries_offset():
    alert = AlertResponse(event_id="e1", timestamp=datetime(2026, 8, 31, 5, 41, 7))
    payload = alert.model_dump_json()
    assert ("+00:00" in payload) or ("Z" in payload), f"expected tz offset in {payload}"


def test_device_and_hub_naive_datetimes_become_utc():
    dev = DeviceResponse(dev_id="d1", dev_name="x", dev_type="TS", is_active=True, last_seen=datetime(2026, 8, 31, 5, 0, 0), created_at=datetime(2026, 8, 31, 5, 0, 0))
    assert dev.last_seen.tzinfo is not None and dev.created_at.tzinfo is not None
    hub = HubResponse(hub_id="h1", hub_name="H", last_seen=datetime(2026, 8, 31, 5, 0, 0))
    assert hub.last_seen.tzinfo is not None
    pt = TelemetryHistoryPoint(timestamp=datetime(2026, 8, 31, 5, 0, 0))
    assert pt.timestamp.tzinfo is not None