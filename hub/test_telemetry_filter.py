"""
hub/test_telemetry_filter.py
============================
Comprehensive test suite for Phase 1: Edge Hub Adaptive Telemetry Filter & SQLite WAL PRAGMAs.

Covers:
1. Pure Functional Evaluator Unit Tests:
   - Deadband thresholds across TS, ATS, AC, and DEFAULT device types.
   - Heartbeat cadence expiration (TS: 300s, ATS: 60s, AC: 120s, DEFAULT: 60s).
   - Instant bypass (0ms delay) on discrete state changes (nowState, autoMode, emergency, etc.).
   - Dynamic transient burst activation (2.0s cadence for 60s duration).
   - Microsecond execution budget (< 0.05ms / 50µs per evaluation).
   - Robust edge cases (NaN, None, missing fields, string floats, timestamp drift, out-of-order packets).
2. SQLite WAL Integration & Write Suppression Invariant:
   - 50 identical steady-state frames during network outage -> EXACTLY 1 row in pending_telemetry (>90% write suppression).
   - State change during outage immediately bypasses deadband and writes row 2 to SQLite WAL.
3. Concurrency & Thread-Safety:
   - Multi-threaded stress testing across simulated concurrent devices.
4. Bounded State Cache:
   - Pruning devices unseen for > 24 hours.
"""

import json
import math
import os
import sys
import threading
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import requests
import pytest

# Ensure hub directory is on path
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
from filter import (
    AdaptiveTelemetryFilter,
    evaluate_telemetry_filter,
    detect_device_type,
    _parse_float,
    get_default_config,
)


@pytest.fixture
def temp_db(tmp_path):
    """Creates a temporary SQLite database for testing edge caching."""
    db_file = str(tmp_path / "test_filter_edge_cache.db")
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
def reset_filter_and_registry():
    """Resets global registry and filter states between tests."""
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.clear()
        main.DEVICE_REGISTRY.clear()
    main.TELEMETRY_FILTER.reset()
    yield
    with main.DEVICE_REGISTRY_LOCK:
        main.WHITELIST_DEVICES.clear()
        main.DEVICE_REGISTRY.clear()
    main.TELEMETRY_FILTER.reset()


# =====================================================================
# 1. Pure Functional Evaluator Unit Tests
# =====================================================================

class TestPureFunctionalEvaluator:
    """Tests the functional core evaluate_telemetry_filter with zero external dependencies."""

    def test_first_packet_always_forwards(self):
        """Invariant: The first packet for any device is ALWAYS forwarded (reason='initial')."""
        payload = {"DEV_ID": "TS_01", "DEV_TYPE": "TS", "temperature": 25.0, "humidity": 60.0}
        now = 1000.0
        should_forward, reason, state = evaluate_telemetry_filter(payload, None, now)

        assert should_forward is True
        assert reason == "initial"
        assert state["last_sent_time"] == now
        assert state["last_sent_values"]["temperature"] == 25.0
        assert state["last_sent_values"]["humidity"] == 60.0
        assert state["burst_until"] == 0.0

    def test_ts_deadband_temperature_and_humidity(self):
        """TS Deadbands: delta_temp >= 0.2°C, delta_hum >= 2.0%."""
        now = 1000.0
        initial_payload = {"DEV_ID": "TS_01", "DEV_TYPE": "TS", "temp": 24.0, "hum": 50.0}
        _, _, state = evaluate_telemetry_filter(initial_payload, None, now)

        # 1. Within deadband (< 0.2°C and < 2.0%) -> Suppressed
        sub_payload = {"DEV_ID": "TS_01", "DEV_TYPE": "TS", "temp": 24.15, "hum": 51.5}
        fwd, reason, state2 = evaluate_telemetry_filter(sub_payload, state, now + 10.0)
        assert fwd is False
        assert reason == "deadband_suppressed"
        # Invariant: last_sent_time and values are preserved on suppression
        assert state2["last_sent_time"] == now
        assert state2["last_sent_values"]["temp"] == 24.0

        # 2. Exceed temperature deadband (delta = 0.25 >= 0.2°C) -> Forwarded
        temp_spike = {"DEV_ID": "TS_01", "DEV_TYPE": "TS", "temp": 24.25, "hum": 51.5}
        fwd, reason, state3 = evaluate_telemetry_filter(temp_spike, state2, now + 20.0)
        assert fwd is True
        assert "deadband_exceeded" in reason
        assert state3["last_sent_time"] == now + 20.0
        assert state3["last_sent_values"]["temp"] == 24.25

        # 3. Exceed humidity deadband (delta = 2.5 >= 2.0%) -> Forwarded
        hum_spike = {"DEV_ID": "TS_01", "DEV_TYPE": "TS", "temp": 24.25, "hum": 54.0}
        fwd, reason, state4 = evaluate_telemetry_filter(hum_spike, state3, now + 30.0)
        assert fwd is True
        assert "deadband_exceeded" in reason
        assert state4["last_sent_time"] == now + 30.0
        assert state4["last_sent_values"]["hum"] == 54.0

    def test_ats_deadband_voltage_battery_current_frequency(self):
        """
        ATS Deadbands:
        - delta_pln_v >= 1.0V
        - delta_gen_v >= 1.0V
        - delta_v_batt >= 0.1V
        - delta_curr >= 0.2A
        - delta_freq >= 0.2Hz
        """
        now = 1000.0
        base_payload = {
            "DEV_ID": "ATS_01",
            "DEV_TYPE": "ATS",
            "v_pln": 220.0,
            "v_genset": 0.0,
            "v_aki": 12.6,
            "current": 5.0,
            "freq": 50.0
        }
        _, _, state = evaluate_telemetry_filter(base_payload, None, now)

        # 1. All sub-deadband -> Suppressed
        sub_payload = {
            "DEV_ID": "ATS_01",
            "DEV_TYPE": "ATS",
            "v_pln": 220.5,   # delta 0.5 < 1.0
            "v_genset": 0.5,  # delta 0.5 < 1.0
            "v_aki": 12.65,   # delta 0.05 < 0.1
            "current": 5.1,   # delta 0.1 < 0.2
            "freq": 50.1      # delta 0.1 < 0.2
        }
        fwd, reason, state = evaluate_telemetry_filter(sub_payload, state, now + 5.0)
        assert fwd is False
        assert reason == "deadband_suppressed"

        # 2. PLN voltage change >= 1.0V -> Forwarded
        pln_shift = dict(sub_payload, v_pln=221.2)
        fwd, reason, state = evaluate_telemetry_filter(pln_shift, state, now + 10.0)
        assert fwd is True
        assert "deadband_exceeded" in reason
        assert state["last_sent_values"]["v_pln"] == 221.2

        # 3. Genset voltage change >= 1.0V -> Forwarded
        gen_shift = dict(pln_shift, v_genset=220.0)
        fwd, reason, state = evaluate_telemetry_filter(gen_shift, state, now + 15.0)
        assert fwd is True
        assert "deadband_exceeded" in reason

        # 4. Battery voltage change >= 0.1V -> Forwarded
        aki_shift = dict(gen_shift, v_aki=12.4)
        fwd, reason, state = evaluate_telemetry_filter(aki_shift, state, now + 20.0)
        assert fwd is True
        assert "deadband_exceeded" in reason

        # 5. Current change >= 0.2A -> Forwarded
        curr_shift = dict(aki_shift, current=5.3)
        fwd, reason, state = evaluate_telemetry_filter(curr_shift, state, now + 25.0)
        assert fwd is True
        assert "deadband_exceeded" in reason

        # 6. Frequency change >= 0.2Hz -> Forwarded
        freq_shift = dict(curr_shift, freq=49.7)
        fwd, reason, state = evaluate_telemetry_filter(freq_shift, state, now + 30.0)
        assert fwd is True
        assert "deadband_exceeded" in reason

    def test_ats_firmware_canonical_keys_pln_genset_aki(self):
        """Verifies deadbands on uppercase firmware keys PLN, GENSET, AKI from WEMOS_ATS.ino."""
        now = 1000.0
        initial = {"DEV_ID": "ATS_WEMOS", "DEV_TYPE": "ATS", "PLN": 220.0, "GENSET": 0.0, "AKI": 12.5}
        _, _, state = evaluate_telemetry_filter(initial, None, now)

        # Minor fluctuations < thresholds -> Suppressed
        fwd, _, state = evaluate_telemetry_filter(
            {"DEV_ID": "ATS_WEMOS", "DEV_TYPE": "ATS", "PLN": 220.6, "GENSET": 0.4, "AKI": 12.54},
            state, now + 5.0
        )
        assert fwd is False

        # Battery drops by 0.15V -> Forwarded
        fwd, reason, state = evaluate_telemetry_filter(
            {"DEV_ID": "ATS_WEMOS", "DEV_TYPE": "ATS", "PLN": 220.6, "GENSET": 0.4, "AKI": 12.35},
            state, now + 10.0
        )
        assert fwd is True
        assert "deadband_exceeded" in reason

    def test_ac_deadband_temperature_and_humidity(self):
        """AC Deadbands: delta_temp >= 0.5°C, delta_hum >= 2.0%."""
        now = 1000.0
        initial = {"DEV_ID": "AC_01", "DEV_TYPE": "AC", "temp": 25.0, "hum": 55.0}
        _, _, state = evaluate_telemetry_filter(initial, None, now)

        # 0.3°C shift < 0.5°C threshold -> Suppressed
        fwd, reason, state = evaluate_telemetry_filter(
            {"DEV_ID": "AC_01", "DEV_TYPE": "AC", "temp": 25.3, "hum": 55.5},
            state, now + 10.0
        )
        assert fwd is False

        # 0.6°C shift >= 0.5°C threshold -> Forwarded
        fwd, reason, state = evaluate_telemetry_filter(
            {"DEV_ID": "AC_01", "DEV_TYPE": "AC", "temp": 25.6, "hum": 55.5},
            state, now + 20.0
        )
        assert fwd is True
        assert "deadband_exceeded" in reason

    def test_heartbeat_cadence_expiration(self):
        """Heartbeat cadence expiration across TS (300s), ATS (60s), AC (120s), and Default (60s)."""
        now = 1000.0
        # TS: 300s steady heartbeat
        ts_init = {"DEV_ID": "TS_HB", "DEV_TYPE": "TS", "temp": 25.0}
        _, _, ts_state = evaluate_telemetry_filter(ts_init, None, now)
        fwd, _, _ = evaluate_telemetry_filter(ts_init, ts_state, now + 299.0)
        assert fwd is False
        fwd, reason, _ = evaluate_telemetry_filter(ts_init, ts_state, now + 300.0)
        assert fwd is True
        assert reason == "heartbeat"

        # ATS: 60s steady heartbeat
        ats_init = {"DEV_ID": "ATS_HB", "DEV_TYPE": "ATS", "v_pln": 220.0}
        _, _, ats_state = evaluate_telemetry_filter(ats_init, None, now)
        fwd, _, _ = evaluate_telemetry_filter(ats_init, ats_state, now + 59.0)
        assert fwd is False
        fwd, reason, _ = evaluate_telemetry_filter(ats_init, ats_state, now + 60.0)
        assert fwd is True
        assert reason == "heartbeat"

        # AC: 120s steady heartbeat
        ac_init = {"DEV_ID": "AC_HB", "DEV_TYPE": "AC", "temp": 22.0}
        _, _, ac_state = evaluate_telemetry_filter(ac_init, None, now)
        fwd, _, _ = evaluate_telemetry_filter(ac_init, ac_state, now + 119.0)
        assert fwd is False
        fwd, reason, _ = evaluate_telemetry_filter(ac_init, ac_state, now + 120.0)
        assert fwd is True
        assert reason == "heartbeat"

        # DEFAULT: 60s steady heartbeat
        def_init = {"DEV_ID": "DEF_HB", "DEV_TYPE": "UNKNOWN_DEVICE", "val": 10.0}
        _, _, def_state = evaluate_telemetry_filter(def_init, None, now)
        fwd, _, _ = evaluate_telemetry_filter(def_init, def_state, now + 59.0)
        assert fwd is False
        fwd, reason, _ = evaluate_telemetry_filter(def_init, def_state, now + 60.0)
        assert fwd is True
        assert reason == "heartbeat"

    def test_instant_bypass_and_dynamic_burst_activation(self):
        """
        Instant Bypass & Dynamic Burst:
        - Discrete state transition forwards immediately (0ms delay).
        - Activates 2.0s burst interval for 60 seconds.
        - Subsequent steady readings report every 2.0s during burst, then revert to 60s steady heartbeat.
        """
        t0 = 1000.0
        payload1 = {"DEV_ID": "ATS_BURST", "DEV_TYPE": "ATS", "nowState": "PLN", "v_pln": 220.0}
        _, _, state = evaluate_telemetry_filter(payload1, None, t0)

        # 1. State change arrives 10s later (PLN -> WAIT_GENSET)
        t_event = t0 + 10.0
        blackout_payload = {"DEV_ID": "ATS_BURST", "DEV_TYPE": "ATS", "nowState": "WAIT_GENSET", "v_pln": 220.0}
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event)

        assert fwd is True
        assert "state_change" in reason
        # Burst active for exactly 60 seconds
        assert state["burst_until"] == t_event + 60.0

        # 2. Reading at t_event + 0.5s with identical values -> Dropped (< 2.0s burst cadence)
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event + 0.5)
        assert fwd is False
        assert reason == "deadband_suppressed"

        # 3. Reading at t_event + 2.1s with identical values -> Forwarded (burst cadence 2.0s elapsed)
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event + 2.1)
        assert fwd is True
        assert reason == "burst_cadence"

        # 4. Reading at t_event + 3.0s -> Dropped (only 0.9s since last sent)
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event + 3.0)
        assert fwd is False

        # 5. Reading at t_event + 4.2s -> Forwarded (2.1s elapsed)
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event + 4.2)
        assert fwd is True
        assert reason == "burst_cadence"

        # 6. After 60 seconds (t_event + 61.0s): Burst mode expired! Reverts to 60s steady heartbeat
        # At t_event + 61.0s, elapsed since last sent (t_event + 4.2s) is 56.8s < 60s steady interval -> Suppressed
        t_post_burst = t_event + 61.0
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_post_burst)
        assert fwd is False
        assert reason == "deadband_suppressed"

        # At t_event + 65.0s, elapsed since last sent is 60.8s >= 60.0s -> Heartbeat triggers
        fwd, reason, state = evaluate_telemetry_filter(blackout_payload, state, t_event + 65.0)
        assert fwd is True
        assert reason == "heartbeat"

    def test_all_state_fields_trigger_instant_bypass(self):
        """All specified discrete state and alert fields must trigger 0ms instant bypass."""
        state_fields = [
            ("nowState", "WAIT", "PLN"),
            ("autoMode", True, False),
            ("emergency", False, True),
            ("pln_relay", 0, 1),
            ("gen_relay", 0, 1),
            ("power", "OFF", "ON"),
            ("state", "IDLE", "RUNNING"),
            ("status", "NORMAL", "FAULT"),
            ("alert", None, "OVERTEMP_ALARM"),
            ("alarm", 0, 1),
            ("AC1_POWER", "OFF", "ON"),
            ("AC2_POWER", "OFF", "ON"),
        ]

        now = 1000.0
        for field, v1, v2 in state_fields:
            p1 = {"DEV_ID": "DEV_TEST", "DEV_TYPE": "ATS", field: v1, "v_pln": 220.0}
            _, _, state = evaluate_telemetry_filter(p1, None, now)

            p2 = {"DEV_ID": "DEV_TEST", "DEV_TYPE": "ATS", field: v2, "v_pln": 220.0}
            fwd, reason, _ = evaluate_telemetry_filter(p2, state, now + 1.0)
            assert fwd is True, f"Field '{field}' failed to trigger instant bypass!"
            assert "state_change" in reason

    def test_edge_cases_nan_none_missing_and_timestamp_drift(self):
        """
        Robustness and security against poison payloads:
        - NaN, None, missing fields must not crash or poison filter state.
        - Backward timestamp drift resets safely without stall.
        - Unparseable payloads fail gracefully.
        """
        now = 1000.0
        init_payload = {"DEV_ID": "DEV_EDGE", "DEV_TYPE": "TS", "temp": 25.0, "hum": 50.0}
        _, _, state = evaluate_telemetry_filter(init_payload, None, now)

        # 1. NaN and unparseable values do NOT overwrite last_sent_values with NaN
        nan_payload = {"DEV_ID": "DEV_EDGE", "DEV_TYPE": "TS", "temp": float("nan"), "hum": "invalid_num"}
        fwd, reason, state_nan = evaluate_telemetry_filter(nan_payload, state, now + 5.0)
        assert fwd is False
        assert state_nan["last_sent_values"]["temp"] == 25.0
        assert not math.isnan(state_nan["last_sent_values"]["temp"])

        # 2. None values handled safely
        none_payload = {"DEV_ID": "DEV_EDGE", "DEV_TYPE": "TS", "temp": None}
        fwd, reason, state_none = evaluate_telemetry_filter(none_payload, state, now + 10.0)
        assert fwd is False

        # 3. Missing fields handled safely
        missing_payload = {"DEV_ID": "DEV_EDGE", "DEV_TYPE": "TS", "hum": 50.5}
        fwd, reason, state_missing = evaluate_telemetry_filter(missing_payload, state, now + 15.0)
        assert fwd is False

        # 4. Backward timestamp drift (e.g. NTP clock adjustment / out-of-order packet)
        drift_payload = {"DEV_ID": "DEV_EDGE", "DEV_TYPE": "TS", "temp": 25.0}
        # Evaluation timestamp is in the past relative to last_sent_time
        fwd, reason, state_drift = evaluate_telemetry_filter(drift_payload, state, now - 50.0)
        assert fwd is True
        assert reason == "timestamp_drift_reset"
        assert state_drift["last_sent_time"] == now - 50.0

        # 5. Invalid / non-dict payload
        fwd, reason, _ = evaluate_telemetry_filter("not_a_dict", state, now)
        assert fwd is False
        assert reason == "invalid_payload"

    def test_performance_microsecond_budget(self):
        """
        Performance Requirement: Functional core evaluation must execute in microseconds (< 0.05ms / 50µs).
        Verifies execution speed across 10,000 iterations.
        """
        payload = {"DEV_ID": "ATS_PERF", "DEV_TYPE": "ATS", "v_pln": 220.1, "nowState": "PLN"}
        _, _, state = evaluate_telemetry_filter(payload, None, 1000.0)

        steady_payload = {"DEV_ID": "ATS_PERF", "DEV_TYPE": "ATS", "v_pln": 220.2, "nowState": "PLN"}
        iterations = 10000

        start = time.perf_counter()
        for i in range(iterations):
            evaluate_telemetry_filter(steady_payload, state, 1000.0 + (i * 0.001))
        duration = time.perf_counter() - start

        avg_microseconds = (duration / iterations) * 1_000_000
        avg_milliseconds = (duration / iterations) * 1000

        print(f"\n[PERF] 10,000 evaluations took {duration:.4f}s: {avg_microseconds:.2f} µs/call ({avg_milliseconds:.4f} ms/call)")
        # Must strictly meet < 0.05ms (50µs)
        assert avg_milliseconds < 0.05, f"Evaluation too slow: {avg_milliseconds:.4f} ms/call > 0.05ms budget"


# =====================================================================
# 2. SQLite WAL Integration & Write Suppression Invariant Tests
# =====================================================================

class TestSQLiteWALIntegrationAndWriteSuppression:
    """Tests the full pipeline from MQTT on_message through the filter into SQLite WAL."""

    def test_write_suppression_invariant_50_frames_single_wal_row(self, temp_db):
        """
        PRIMARY INVARIANT:
        Ingesting 50 identical steady-state frames during network outage results in
        EXACTLY 1 row inserted into pending_telemetry (>90% write suppression locked).
        """
        dev_id = "A4:CF:12:F1:C0:ATS1"
        with main.DEVICE_REGISTRY_LOCK:
            main.WHITELIST_DEVICES.add(dev_id)
            main.DEVICE_REGISTRY[dev_id] = {
                "dev_id": dev_id,
                "dev_name": "hs109-ats-01",
                "dev_type": "ATS",
                "hub_name": "hs109rs"
            }

        steady_frame = {
            "DEV_ID": dev_id,
            "DEV_NAME": "hs109-ats-01",
            "DEV_TYPE": "ATS",
            "STATE": "PLN",
            "nowState": "PLN",
            "PLN": 220.4,
            "GENSET": 0.0,
            "AKI": 12.6,
            "AUTO_MODE": True,
            "EMERGENCY": False
        }

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "hs109rs/ats/telemetry"
        mock_msg.payload = json.dumps(steady_frame).encode("utf-8")

        # Simulate permanent network outage during the test
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Network outage")):
            for i in range(50):
                main.on_message(mock_client, None, mock_msg)

        # Inspect SQLite WAL pending_telemetry rows
        conn = main.create_db_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT id, payload, created_at FROM pending_telemetry")
        rows = cursor.fetchall()
        conn.close()

        # EXACTLY 1 row must be stored!
        assert len(rows) == 1, f"Write suppression invariant violated! Expected 1 row, found {len(rows)}"

        # Verify the single row payload
        saved = json.loads(rows[0][1])
        assert saved["DEV_ID"] == dev_id
        assert saved["PLN"] == 220.4

        # Calculate exact suppression percentage
        suppression_rate = ((50 - len(rows)) / 50.0) * 100.0
        assert suppression_rate >= 90.0
        print(f"\n[INVARIANT VERIFIED] Ingested 50 steady-state frames -> exactly 1 SQLite row written. Write suppression: {suppression_rate:.1f}%")

    def test_state_change_bypass_persists_immediately_during_outage(self, temp_db):
        """
        State change bypass test:
        Even when numeric readings stay within deadband, a discrete state transition
        must immediately bypass suppression and persist to SQLite WAL.
        """
        dev_id = "A4:CF:12:F1:C0:ATS2"
        with main.DEVICE_REGISTRY_LOCK:
            main.WHITELIST_DEVICES.add(dev_id)

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "hs109rs/ats/telemetry"

        frame_pln = {
            "DEV_ID": dev_id,
            "DEV_TYPE": "ATS",
            "nowState": "PLN",
            "v_pln": 220.0
        }

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Outage")):
            # 1. First frame (Row 1 written)
            mock_msg.payload = json.dumps(frame_pln).encode("utf-8")
            main.on_message(mock_client, None, mock_msg)

            # 2. Ten identical frames (Suppressed, still 1 row)
            for _ in range(10):
                main.on_message(mock_client, None, mock_msg)

            conn = main.create_db_connection(temp_db)
            count = conn.execute("SELECT COUNT(*) FROM pending_telemetry").fetchone()[0]
            conn.close()
            assert count == 1

            # 3. State change frame: nowState changes to "WAIT_GENSET" with same voltage
            frame_genset = {
                "DEV_ID": dev_id,
                "DEV_TYPE": "ATS",
                "nowState": "WAIT_GENSET",
                "v_pln": 220.0
            }
            mock_msg.payload = json.dumps(frame_genset).encode("utf-8")
            main.on_message(mock_client, None, mock_msg)

        # 4. State change must have immediately written Row 2!
        conn = main.create_db_connection(temp_db)
        rows = conn.execute("SELECT id, payload FROM pending_telemetry ORDER BY id ASC").fetchall()
        conn.close()

        assert len(rows) == 2
        p1 = json.loads(rows[0][1])
        p2 = json.loads(rows[1][1])
        assert p1["nowState"] == "PLN"
        assert p2["nowState"] == "WAIT_GENSET"

    def test_commands_and_acks_are_never_filtered(self):
        """Downlink commands and ACKs must bypass telemetry filter completely."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "hs109rs/ac/command"
        mock_msg.payload = json.dumps({"target": "AC1", "action": "ON"}).encode("utf-8")

        with patch("requests.post") as mock_post:
            main.on_message(mock_client, None, mock_msg)
            # Should have returned immediately without sending as telemetry
            assert mock_post.call_count == 0


# =====================================================================
# 3. Concurrency & Thread-Safety Tests
# =====================================================================

class TestFilterConcurrencyAndThreadSafety:
    """Verifies thread safety of AdaptiveTelemetryFilter under multi-threaded concurrency."""

    def test_concurrent_threads_passing_frames(self):
        """
        Spawns 10 concurrent threads passing 100 frames each for distinct and shared devices.
        Ensures zero deadlocks, race conditions, or unhandled exceptions.
        """
        filter_instance = AdaptiveTelemetryFilter()
        errors = []

        def worker_task(thread_id: int):
            try:
                for seq in range(100):
                    # Each thread sends alternating updates for its own device and a shared device
                    dev_own = f"DEV_THREAD_{thread_id:02d}"
                    dev_shared = "DEV_SHARED"

                    filter_instance.evaluate(
                        dev_own,
                        {"DEV_ID": dev_own, "DEV_TYPE": "TS", "temp": 20.0 + (seq * 0.05)}
                    )
                    filter_instance.evaluate(
                        dev_shared,
                        {"DEV_ID": dev_shared, "DEV_TYPE": "ATS", "v_pln": 220.0, "nowState": "PLN" if seq % 10 != 0 else "WAIT"}
                    )
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency errors occurred: {errors}"
        # Shared device state must exist and be valid
        shared_state = filter_instance.get_state("DEV_SHARED")
        assert shared_state is not None
        assert "last_sent_time" in shared_state


# =====================================================================
# 4. Bounded State Cache & Pruning Tests
# =====================================================================

class TestBoundedStateCache:
    """Verifies memory footprint remains strictly bounded via 24h stale device pruning."""

    def test_prune_devices_unseen_for_more_than_24h(self):
        """Devices unseen for > 24 hours (86400s) are pruned from in-memory cache."""
        filter_instance = AdaptiveTelemetryFilter()
        t_base = 1_000_000.0

        # Device 1: Active 25 hours ago (Stale)
        filter_instance.evaluate("STALE_DEV_1", {"DEV_ID": "STALE_DEV_1", "temp": 20.0}, now=t_base - 90000.0)

        # Device 2: Active 2 hours ago (Fresh)
        filter_instance.evaluate("FRESH_DEV_2", {"DEV_ID": "FRESH_DEV_2", "temp": 21.0}, now=t_base - 7200.0)

        # Device 3: Active right now (Fresh)
        filter_instance.evaluate("FRESH_DEV_3", {"DEV_ID": "FRESH_DEV_3", "temp": 22.0}, now=t_base)

        # Prune stale devices
        pruned_count = filter_instance.prune_stale_devices(max_age_seconds=86400.0, now=t_base)
        assert pruned_count == 1

        # STALE_DEV_1 should be gone, FRESH devices remain
        assert filter_instance.get_state("STALE_DEV_1") is None
        assert filter_instance.get_state("FRESH_DEV_2") is not None
        assert filter_instance.get_state("FRESH_DEV_3") is not None
