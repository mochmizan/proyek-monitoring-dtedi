#!/usr/bin/env python3
import time
import random
import requests
import json
import sys

import os
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000/api/iot")
HUB_ID = os.getenv("HUB_NAME", "hs109rs-hub-01")
HUB_KEY = os.getenv("HUB_KEY")
if not HUB_KEY:
    raise SystemExit("HUB_KEY env required. No hardcoded live secret.")

DEVICES = [
    {"dev_id": "AA:BB:CC:11:22:01", "dev_name": "Server Room Temp", "dev_type": "TS", "base_temp": 24.5, "base_hum": 55.0},
    {"dev_id": "AA:BB:CC:11:22:03", "dev_name": "Network Temp", "dev_type": "TS", "base_temp": 26.8, "base_hum": 60.0},
    {"dev_id": "AA:BB:CC:11:22:04", "dev_name": "Battery Temp", "dev_type": "TS", "base_temp": 23.2, "base_hum": 52.0},
]

def stream_loop(interval=3):
    print(f"Starting live telemetry streamer (pushing every {interval}s to {SERVER_URL})...")
    headers = {
        "Content-Type": "application/json",
        "X-Hub-ID": HUB_ID,
        "X-Hub-Key": HUB_KEY
    }

    current_temps = {d["dev_id"]: d["base_temp"] for d in DEVICES}
    current_hums = {d["dev_id"]: d["base_hum"] for d in DEVICES}

    while True:
        try:
            for dev in DEVICES:
                dev_id = dev["dev_id"]
                drift_temp = random.uniform(-0.15, 0.15)
                drift_hum = random.uniform(-0.25, 0.25)
                current_temps[dev_id] = round(max(18.0, min(38.0, current_temps[dev_id] + drift_temp)), 2)
                current_hums[dev_id] = round(max(30.0, min(90.0, current_hums[dev_id] + drift_hum)), 2)

                payload = {
                    "HUB_NAME": "hs109rs-hub-01",
                    "DEV_ID": dev_id,
                    "DEV_NAME": dev["dev_name"],
                    "DEV_TYPE": "TS",
                    "TEMP": current_temps[dev_id],
                    "HUMID": current_hums[dev_id]
                }

                res = requests.post(SERVER_URL, json=payload, headers=headers, timeout=2)
                if res.status_code != 200:
                    print(f"Failed to post {dev_id}: {res.status_code} {res.text}")

            print(f"[{time.strftime('%H:%M:%S')}] Pushed telemetry: Server Temp={current_temps['AA:BB:CC:11:22:01']} C, Network Temp={current_temps['AA:BB:CC:11:22:03']} C")
        except Exception as e:
            print(f"Streamer error: {e}")

        time.sleep(interval)

if __name__ == "__main__":
    stream_loop()
