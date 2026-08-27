#!/usr/bin/env python3
"""
tools/mock_publishers.py
Mock Telemetry Publisher & Command Listener for HubGate V5 IoT Ecosystem.

Simulates ESP8266/WEMOS nodes publishing telemetry for:
- TS (Temperature Sensor) -> hs109rs/ts/data
- ATS (Automatic Transfer Switch) -> hs109rs/ats/data
- AC (Dual Air Conditioner Controller) -> hs109rs/ac/data

Also subscribes to downlink command topics (hs109rs/+/command) to verify end-to-end command flow.
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from typing import Any, Dict, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt package is required. Install via: pip install paho-mqtt", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("MockPublisher")

# Defaults matching production firmware
DEFAULT_HUB_NAME = os.getenv("HUB_NAME", "hs109rs-hub-01")
DEFAULT_MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
DEFAULT_MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_MQTT_USER = os.getenv("MQTT_USER", "hubadmin")
DEFAULT_MQTT_PASS = os.getenv("MQTT_PASS")  # no hardcoded fallback; use --password or MQTT_PASS env (dev: export MQTT_PASS=hubadmin_local_secret_pass_2026)

DEVICE_PROFILES = {
    "ts": {
        "dev_id": "AA:BB:CC:DD:EE:01",
        "dev_name": "hs109-ts-01",
        "dev_type": "TS",
        "topic": "hs109rs/ts/data",
        "cmd_topic": "hs109rs/ts/command",
    },
    "ats": {
        "dev_id": "AA:BB:CC:DD:EE:02",
        "dev_name": "hs109-ats-01",
        "dev_type": "ATS",
        "topic": "hs109rs/ats/data",
        "cmd_topic": "hs109rs/ats/command",
    },
    "ac": {
        "dev_id": "AA:BB:CC:DD:EE:03",
        "dev_name": "hs109-ac-01",
        "dev_type": "AC",
        "topic": "hs109rs/ac/data",
        "cmd_topic": "hs109rs/ac/command",
    }
}


def build_ts_payload(
    hub_name: str = DEFAULT_HUB_NAME,
    dev_id: str = DEVICE_PROFILES["ts"]["dev_id"],
    dev_name: str = DEVICE_PROFILES["ts"]["dev_name"],
    temp: Optional[float] = None,
    humid: Optional[float] = None
) -> Dict[str, Any]:
    """Generates TS telemetry payload matching schemasv5.TSData."""
    return {
        "HUB_NAME": hub_name,
        "DEV_ID": dev_id,
        "DEV_NAME": dev_name,
        "DEV_TYPE": "TS",
        "TEMP": round(temp if temp is not None else random.uniform(22.0, 28.5), 2),
        "HUMID": round(humid if humid is not None else random.uniform(45.0, 65.0), 2)
    }


def build_ats_payload(
    hub_name: str = DEFAULT_HUB_NAME,
    dev_id: str = DEVICE_PROFILES["ats"]["dev_id"],
    dev_name: str = DEVICE_PROFILES["ats"]["dev_name"],
    state: str = "PLN",
    pln: Optional[float] = None,
    genset: Optional[float] = None,
    aki: Optional[float] = None,
    rem_hour: float = 0.0,
    rem_min: float = 0.0,
    rem_sec: float = 0.0,
    auto_mode: bool = True,
    emergency: bool = False
) -> Dict[str, Any]:
    """Generates ATS telemetry payload matching schemasv5.ATSData."""
    if pln is None:
        pln = round(random.uniform(218.0, 224.0), 1) if state == "PLN" else 0.0
    if genset is None:
        genset = round(random.uniform(219.0, 222.0), 1) if state == "GENSET" else 0.0
    if aki is None:
        aki = round(random.uniform(12.4, 13.6), 2)

    return {
        "HUB_NAME": hub_name,
        "DEV_ID": dev_id,
        "DEV_NAME": dev_name,
        "DEV_TYPE": "ATS",
        "STATE": state,
        "PLN": float(pln),
        "GENSET": float(genset),
        "AKI": float(aki),
        "REM_HOUR": float(rem_hour),
        "REM_MIN": float(rem_min),
        "REM_SEC": float(rem_sec),
        "AUTO_MODE": bool(auto_mode),
        "EMERGENCY": bool(emergency)
    }


def build_ac_payload(
    hub_name: str = DEFAULT_HUB_NAME,
    dev_id: str = DEVICE_PROFILES["ac"]["dev_id"],
    dev_name: str = DEVICE_PROFILES["ac"]["dev_name"],
    ac1_power: str = "ON",
    ac1_temp: float = 24.0,
    ac2_power: str = "OFF",
    ac2_temp: float = 24.0,
    temp: Optional[float] = None,
    humid: Optional[float] = None
) -> Dict[str, Any]:
    """Generates AC telemetry payload matching schemasv5.ACData."""
    return {
        "HUB_NAME": hub_name,
        "DEV_ID": dev_id,
        "DEV_NAME": dev_name,
        "DEV_TYPE": "AC",
        "AC1_POWER": ac1_power.upper(),
        "AC1_TEMP": float(ac1_temp),
        "AC2_POWER": ac2_power.upper(),
        "AC2_TEMP": float(ac2_temp),
        "TEMP": round(temp if temp is not None else random.uniform(23.0, 26.0), 2),
        "HUMID": round(humid if humid is not None else random.uniform(50.0, 60.0), 2)
    }


class MockMqttNode:
    """MQTT Client wrapper supporting Paho v1 & v2 for mock publishing and command listening."""

    def __init__(
        self,
        host: str = DEFAULT_MQTT_HOST,
        port: int = DEFAULT_MQTT_PORT,
        user: str = DEFAULT_MQTT_USER,
        password: str = DEFAULT_MQTT_PASS,
        client_id: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client_id = client_id or f"mock_node_{random.randint(1000, 9999)}"
        self.received_commands = []

        # Paho MQTT Client version compatibility
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=self.client_id)
        else:
            self.client = mqtt.Client(client_id=self.client_id)

        if self.user and self.password:
            self.client.username_pw_set(self.user, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info(f"[CONNECTED] Connected to MQTT broker at {self.host}:{self.port} as {self.client_id}")
            # Subscribe to all downlink command topics for monitoring
            client.subscribe("hs109rs/+/command")
            logger.info("[SUBSCRIBED] Listening on 'hs109rs/+/command'")
        else:
            logger.error(f"[CONNECT FAILED] Broker rejected connection with return code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
            logger.info(f"[COMMAND RECEIVED] Topic: {msg.topic} | Payload: {payload_str}")
            parsed = json.loads(payload_str)
            self.received_commands.append({"topic": msg.topic, "payload": parsed, "raw": payload_str})
        except Exception as e:
            logger.warning(f"[COMMAND RAW] Topic: {msg.topic} | Raw: {msg.payload} (decode err: {e})")
            self.received_commands.append({"topic": msg.topic, "payload": None, "raw": msg.payload})

    def connect(self, timeout: int = 5) -> bool:
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
            start = time.time()
            while not self._connected and (time.time() - start) < timeout:
                time.sleep(0.1)
            return self._connected
        except Exception as e:
            logger.error(f"[MQTT ERROR] Connection exception: {e}")
            return False

    def publish_json(self, topic: str, payload: Dict[str, Any]) -> bool:
        payload_str = json.dumps(payload)
        res = self.client.publish(topic, payload_str)
        if hasattr(res, "rc"):
            success = (res.rc == mqtt.MQTT_ERR_SUCCESS)
        else:
            success = True

        if success:
            logger.info(f"[PUBLISHED] -> {topic}: {payload_str}")
        else:
            logger.error(f"[PUBLISH FAILED] -> {topic}")
        return success

    def disconnect(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("[DISCONNECTED] Disconnected from MQTT broker.")
        except Exception:
            pass


def run_publisher_cli():
    parser = argparse.ArgumentParser(description="HubGate V5 Mock Telemetry Publisher & Command Listener")
    parser.add_argument("--broker", "-b", default=DEFAULT_MQTT_HOST, help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", "-p", type=int, default=DEFAULT_MQTT_PORT, help="MQTT broker port (default: 1883)")
    parser.add_argument("--user", "-u", default=DEFAULT_MQTT_USER, help="MQTT username")
    parser.add_argument("--password", "-P", default=DEFAULT_MQTT_PASS, help="MQTT password")
    parser.add_argument("--hub-name", default=DEFAULT_HUB_NAME, help="Hub name prefix (default: hs109rs-hub-01)")
    parser.add_argument("--type", "-t", choices=["ts", "ats", "ac", "all"], default="all", help="Device type to publish")
    parser.add_argument("--loop", "-l", action="store_true", help="Continuously publish in a loop")
    parser.add_argument("--interval", "-i", type=float, default=5.0, help="Interval in seconds between publishes (default: 5.0)")
    parser.add_argument("--count", "-n", type=int, default=None, help="Number of loops to execute (default: infinite)")
    parser.add_argument("--listen", action="store_true", help="Keep running to listen for incoming commands")

    # Value Overrides
    parser.add_argument("--temp", type=float, default=None, help="Override temperature value")
    parser.add_argument("--humid", type=float, default=None, help="Override humidity value")
    parser.add_argument("--state", default="PLN", choices=["PLN", "GENSET", "MANUAL", "OFF"], help="ATS state")
    parser.add_argument("--pln", type=float, default=None, help="ATS PLN voltage")
    parser.add_argument("--genset", type=float, default=None, help="ATS Genset voltage")
    parser.add_argument("--aki", type=float, default=None, help="ATS Battery voltage")
    parser.add_argument("--auto-mode", action=argparse.BooleanOptionalAction, default=True, help="ATS auto mode flag")
    parser.add_argument("--emergency", action="store_true", help="ATS emergency mode flag")

    args = parser.parse_args()

    node = MockMqttNode(
        host=args.broker,
        port=args.port,
        user=args.user,
        password=args.password
    )

    logger.info(f"Connecting to MQTT broker {args.broker}:{args.port}...")
    if not node.connect():
        logger.error("Could not connect to MQTT broker. Ensure Mosquitto container is running.")
        sys.exit(1)

    types_to_send = ["ts", "ats", "ac"] if args.type == "all" else [args.type]

    def send_batch():
        for dev_t in types_to_send:
            if dev_t == "ts":
                payload = build_ts_payload(
                    hub_name=args.hub_name,
                    temp=args.temp,
                    humid=args.humid
                )
                node.publish_json(DEVICE_PROFILES["ts"]["topic"], payload)
            elif dev_t == "ats":
                payload = build_ats_payload(
                    hub_name=args.hub_name,
                    state=args.state,
                    pln=args.pln,
                    genset=args.genset,
                    aki=args.aki,
                    auto_mode=args.auto_mode,
                    emergency=args.emergency
                )
                node.publish_json(DEVICE_PROFILES["ats"]["topic"], payload)
            elif dev_t == "ac":
                payload = build_ac_payload(
                    hub_name=args.hub_name,
                    temp=args.temp,
                    humid=args.humid
                )
                node.publish_json(DEVICE_PROFILES["ac"]["topic"], payload)

    try:
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"--- Telemetry Publish Cycle #{iteration} ---")
            send_batch()

            if not args.loop and not args.listen:
                break

            if args.count and iteration >= args.count:
                break

            time.sleep(args.interval)

        if args.listen:
            logger.info("Listening for commands. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\nStopping mock publisher...")
    finally:
        node.disconnect()


if __name__ == "__main__":
    run_publisher_cli()
