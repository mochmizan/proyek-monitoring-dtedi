import os
import sys
import json
import time
import threading
import logging
import re
import sqlite3
import requests
import urllib3
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from contextlib import contextmanager

# Disable peringatan SSL Unverified HTTPS untuk IP lokal
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup Logging Standard Output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Load Konfigurasi Lingkungan (.env) jika tersedia
load_dotenv()

# Fail daemon startup immediately if environment variables MQTT_PASS or HUB_KEY are missing or match weak placeholder defaults.
MQTT_PASS = os.getenv("MQTT_PASS")
HUB_KEY = os.getenv("HUB_KEY")
ALLOW_INSECURE_DEV_KEYS = os.getenv("ALLOW_INSECURE_DEV_KEYS", "false").lower() in ("true", "1", "yes")

WEAK_MQTT_PASS = "414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1"
WEAK_HUB_KEY = "70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4"

if not MQTT_PASS:
    raise RuntimeError("MQTT_PASS environment variable is missing.")
if MQTT_PASS == WEAK_MQTT_PASS and not ALLOW_INSECURE_DEV_KEYS:
    raise RuntimeError("MQTT_PASS matches weak placeholder default. Set ALLOW_INSECURE_DEV_KEYS=true for local dev.")

if not HUB_KEY:
    raise RuntimeError("HUB_KEY environment variable is missing.")
if HUB_KEY == WEAK_HUB_KEY and not ALLOW_INSECURE_DEV_KEYS:
    raise RuntimeError("HUB_KEY matches weak placeholder default. Set ALLOW_INSECURE_DEV_KEYS=true for local dev.")


# ==========================================
# KONFIGURASI MQTT BROKER LOKAL
# ==========================================
MQTT_HOST  = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT  = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER  = os.getenv("MQTT_USER", "hubadmin")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hs109rs/#")

# Topic khusus Downlink Command AC (legacy compatibility)
AC_COMMAND_TOPIC = "hs109rs/ac/command"

# ==========================================
# KONFIGURASI CENTRAL SERVER FASTAPI
# ==========================================
SERVER_URL         = os.getenv("SERVER_URL", "https://192.168.72.245/api/iot")
SERVER_DEVICES_URL = os.getenv("SERVER_DEVICES_URL", "https://192.168.72.245/api/devices")

# TLS Certificate configuration
TLS_CERT_PATH = os.getenv("TLS_CERT_PATH")
if not TLS_CERT_PATH:
    TLS_CERT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cert.crt")

# Derive command URLs
base_api = SERVER_DEVICES_URL.rsplit("/", 1)[0] if SERVER_DEVICES_URL else "https://192.168.72.245/api"
SERVER_COMMANDS_URL = os.getenv("SERVER_COMMANDS_URL", f"{base_api}/hub/commands")
SERVER_UNAPPROVED_URL = os.getenv("SERVER_UNAPPROVED_URL", f"{base_api}/iot/unapproved")

# Debounce tracker for unapproved device alerts
REPORTED_UNAPPROVED_MACS = {}

# Identitas Hub (Wajib cocok dengan hub_table di Database Server)
HUB_ID  = os.getenv("HUB_ID", "hs109rs-hub-01")

# ==========================================
# OFFLINE STORAGE CONFIGURATION (SQLite WAL)
# ==========================================
EDGE_CACHE_DB_PATH = os.getenv("EDGE_CACHE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_cache.db"))
DB_PATH = EDGE_CACHE_DB_PATH

REPLAY_BATCH_SIZE = int(os.getenv("REPLAY_BATCH_SIZE", "25"))
REPLAY_PACING_DELAY = float(os.getenv("REPLAY_PACING_DELAY", "0.35"))
REPLAY_INTERVAL = float(os.getenv("REPLAY_INTERVAL", "5.0"))
MAX_PENDING_ROWS = int(os.getenv("MAX_PENDING_ROWS", "20000"))

# RAM Cache untuk Whitelist dan Registry Perangkat Aktif
WHITELIST_DEVICES = set()
DEVICE_REGISTRY = {}
DEVICE_REGISTRY_LOCK = threading.Lock()


@contextmanager
def get_db_conn(db_path: str = None):
    """
    Context manager that creates, configures, and GUARANTEES closing of SQLite connections.
    Prevents file descriptor leaks ('Too many open files').
    """
    target_path = db_path or EDGE_CACHE_DB_PATH
    conn = sqlite3.connect(target_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def create_db_connection(db_path: str = None) -> sqlite3.Connection:
    target_path = db_path or EDGE_CACHE_DB_PATH
    conn = sqlite3.connect(target_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


def init_db(db_path: str = None):
    """Initializes the database schema if not present."""
    target_path = db_path or EDGE_CACHE_DB_PATH
    with get_db_conn(target_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_telemetry(created_at);")
        conn.commit()


def enqueue_pending_telemetry(payload_dict: dict, db_path: str = None) -> bool:
    """Stores telemetry payload in SQLite WAL cache on upstream failure with bounded capacity.

    Note: at-least-once replay semantics; server-side deduplication recommended on
    (DEV_ID, created_at) to handle duplicate delivery after replay/retries.
    """
    target_path = db_path or EDGE_CACHE_DB_PATH
    try:
        payload_str = json.dumps(payload_dict)
        with get_db_conn(target_path) as conn:
            # 7-day TTL cleanup to protect SD card storage
            cutoff = time.time() - (7 * 86400)
            conn.execute("DELETE FROM pending_telemetry WHERE created_at < ?", (cutoff,))

            # Bounded-queue: prune oldest rows if at capacity to protect SD card storage
            cursor = conn.execute("SELECT COUNT(*) FROM pending_telemetry")
            count = cursor.fetchone()[0]
            if count >= MAX_PENDING_ROWS:
                overflow = count - MAX_PENDING_ROWS + 1
                conn.execute("DELETE FROM pending_telemetry WHERE id IN (SELECT id FROM pending_telemetry ORDER BY id ASC LIMIT ?)", (overflow,))

            # Enqueue new record (at-least-once replay; server dedup recommended on (DEV_ID, created_at))
            conn.execute(
                "INSERT INTO pending_telemetry (payload, created_at) VALUES (?, ?)",
                (payload_str, time.time())
            )
            conn.commit()
        logging.info(f"[CACHE STORED] Buffered telemetry for {payload_dict.get('DEV_ID')}")
        return True
    except Exception as e:
        logging.error(f"[CACHE WRITE ERROR] Failed to buffer telemetry: {e}")
        return False


def replay_backlog_batch(db_path: str = None, batch_size: int = REPLAY_BATCH_SIZE, pacing_delay: float = REPLAY_PACING_DELAY) -> int:
    """
    Drains up to `batch_size` pending telemetry records from SQLite WAL cache in FIFO order.
    Returns the number of successfully replayed records.
    """
    target_path = db_path or EDGE_CACHE_DB_PATH
    try:
        with get_db_conn(target_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, payload FROM pending_telemetry ORDER BY id ASC LIMIT ?",
                (batch_size,)
            )
            rows = cursor.fetchall()
    except Exception as e:
        logging.error(f"[REPLAY DB READ ERROR] {e}")
        return 0

    if not rows:
        return 0

    logging.info(f"[REPLAY WORKER] Draining batch of {len(rows)} pending telemetry records...")
    replayed_count = 0

    for record_id, payload_str in rows:
        try:
            payload_dict = json.loads(payload_str)
        except json.JSONDecodeError:
            # Corrupted payload: prune to prevent replay loop lock
            logging.error(f"[REPLAY CORRUPT] Deleting unparseable record id={record_id}")
            try:
                with get_db_conn(target_path) as conn:
                    conn.execute("DELETE FROM pending_telemetry WHERE id = ?", (record_id,))
                    conn.commit()
            except Exception as e:
                logging.error(f"[REPLAY DB DELETE ERROR] {e}")
            continue

        try:
            response = requests.post(
                SERVER_URL,
                json=payload_dict,
                headers=get_hub_headers(),
                verify=TLS_CERT_PATH,
                timeout=5
            )

            if response.status_code in (200, 201):
                with get_db_conn(target_path) as conn:
                    conn.execute("DELETE FROM pending_telemetry WHERE id = ?", (record_id,))
                    conn.commit()
                replayed_count += 1
                logging.info(f"[REPLAY SUCCESS] Replayed record id={record_id} ({payload_dict.get('DEV_ID')})")
                if pacing_delay > 0:
                    time.sleep(pacing_delay)

            elif response.status_code == 429:
                logging.warning("[REPLAY 429] Rate limit hit on server. Backing off 15s...")
                time.sleep(15)
                break

            elif response.status_code in (400, 403, 422):
                logging.error(f"[REPLAY REJECTED] Server rejected record id={record_id} (HTTP {response.status_code}): {response.text}. Quarantining.")
                with get_db_conn(target_path) as conn:
                    conn.execute("DELETE FROM pending_telemetry WHERE id = ?", (record_id,))
                    conn.commit()

            else:
                logging.warning(f"[REPLAY SERVER ERR] Server responded HTTP {response.status_code}. Pausing replay batch.")
                break

        except (requests.exceptions.RequestException, Exception) as net_err:
            logging.warning(f"[REPLAY OFFLINE] Network unavailable or upstream error ({net_err}). Pausing replay.")
            break

    return replayed_count


def replay_backlog_thread(db_path: str = None, stop_event: threading.Event = None):
    """Background worker daemon thread that continuously drains offline WAL cache."""
    logging.info("[REPLAY WORKER] Offline replay worker started.")
    while stop_event is None or not stop_event.is_set():
        try:
            replayed = replay_backlog_batch(db_path=db_path)
            if replayed == 0:
                if stop_event:
                    stop_event.wait(REPLAY_INTERVAL)
                else:
                    time.sleep(REPLAY_INTERVAL)
        except Exception as e:
            logging.error(f"[REPLAY LOOP ERROR] Unexpected error: {e}")
            if stop_event:
                stop_event.wait(REPLAY_INTERVAL)
            else:
                time.sleep(REPLAY_INTERVAL)


def get_hub_headers():
    """Menghasilkan HTTP Header resmi yang diwajibkan oleh verify_hub_identity FastAPI."""
    return {
        "Content-Type": "application/json",
        "X-Hub-ID": HUB_ID,
        "X-Hub-Key": HUB_KEY
    }


def sync_whitelist_once() -> bool:
    """Mengambil daftar whitelist perangkat resmi khusus untuk Hub ini dari Server sekali."""
    global WHITELIST_DEVICES, DEVICE_REGISTRY
    try:
        # Panggil Endpoint MURNI via Headers (TANPA Query Params agar tidak error 422)
        response = requests.get(
            SERVER_DEVICES_URL,
            headers=get_hub_headers(),
            verify=TLS_CERT_PATH,
            timeout=5
        )

        if response.status_code == 200:
            devices = response.json()
            new_whitelist = set()
            new_registry = {}
            for dev in devices:
                dev_id = str(dev.get("DEV_ID") or dev.get("dev_id") or "").strip().upper()
                if not dev_id:
                    continue
                dev_name = dev.get("DEV_NAME") or dev.get("dev_name") or ""
                dev_type = str(dev.get("DEV_TYPE") or dev.get("dev_type") or "ATS").strip().upper()
                hub_name = dev.get("HUB_NAME") or dev.get("hub_name") or (HUB_ID.split("-")[0] if "-" in HUB_ID else HUB_ID)
                new_whitelist.add(dev_id)
                new_registry[dev_id] = {
                    "dev_id": dev_id,
                    "dev_name": dev_name,
                    "dev_type": dev_type,
                    "hub_name": hub_name
                }
            with DEVICE_REGISTRY_LOCK:
                DEVICE_REGISTRY = new_registry
                WHITELIST_DEVICES = new_whitelist
            logging.info(f"[SYNC SUCCESS] Device registry & whitelist diperbarui untuk ({HUB_ID}). Terdaftar: {len(WHITELIST_DEVICES)} perangkat.")
            return True
        else:
            logging.warning(f"[SYNC FAILED] Server merespon HTTP {response.status_code}: {response.text}")
            return False

    except Exception as e:
        logging.error(f"[SYNC ERROR] Gagal menghubungkan ke server backend: {e}")
        return False


def sync_whitelist():
    """Mengambil daftar whitelist perangkat resmi khusus untuk Hub ini dari Server secara berkala."""
    while True:
        sync_whitelist_once()
        time.sleep(30)  # Re-sync tiap 30 detik


def validate_ac_payload(payload: dict) -> tuple[bool, str]:
    """Validates AC command payload according to WEMOS_AC.ino firmware contract."""
    target = str(payload.get("target") or payload.get("AC_NUMBER") or "").upper()
    action = str(payload.get("action") or payload.get("AC_COMMAND") or "").upper()

    if target not in ("AC1", "AC2"):
        return False, f"Invalid target AC: '{target}'. Must be 'AC1' or 'AC2'."

    if action in ("ON", "OFF"):
        return True, ""

    if action == "SET_TEMP":
        temp_val = payload.get("temp")
        if temp_val is not None and 16 <= int(temp_val) <= 30:
            return True, ""
        return False, f"Invalid temperature: '{temp_val}'. Must be 16-30."

    temp_match = re.match(r"^TEMP\s+(\d+)$", action)
    if temp_match:
        temp_val = int(temp_match.group(1))
        if 16 <= temp_val <= 30:
            return True, ""
        return False, f"Temperature {temp_val}°C out of valid range (16-30°C)."

    return False, f"Invalid AC action: '{action}'. Must be ON, OFF, or SET_TEMP (16-30)."


def validate_ats_payload(payload: dict) -> tuple[bool, str]:
    """Validates ATS command payload according to fixed_wemos_mqtt_raspi.ino contract."""
    valid_keys = {"mode", "start_genset", "reset"}
    if not any(k in payload for k in valid_keys):
        return False, "Payload must contain at least one of 'mode', 'start_genset', or 'reset'."
    return True, ""


def derive_command_topic(dev_id: str, payload_dict: dict = None) -> str:
    """
    Dynamically resolves MQTT downlink topic for a command based on DEVICE_REGISTRY
    or infers dev_type from payload structure. Format: {hub_name}/{dev_type}/command
    """
    dev_id_clean = str(dev_id or "").strip().upper()
    with DEVICE_REGISTRY_LOCK:
        device_info = DEVICE_REGISTRY.get(dev_id_clean)

    if device_info:
        dev_type = str(device_info.get("dev_type", "ATS")).lower()
        raw_hub = device_info.get("hub_name") or HUB_ID
        hub_name = raw_hub.split("-")[0] if "-" in raw_hub else raw_hub
    else:
        # Fallback inference if device is not in local registry
        payload = payload_dict or {}
        if any(k in payload for k in ("target", "action", "AC_NUMBER", "AC_COMMAND")):
            dev_type = "ac"
        elif any(k in payload for k in ("mode", "start_genset", "reset")):
            dev_type = "ats"
        else:
            dev_type = "ats"
        hub_name = HUB_ID.split("-")[0] if "-" in HUB_ID else HUB_ID

    return f"{hub_name}/{dev_type}/command"


def send_ac_command(client, ac_number: str, command: str, temp_val: int = None):
    """Mengirimkan perintah kontrol AC ke topik MQTT hs109rs/ac/command."""
    ac_number = ac_number.upper()
    command = command.upper()

    if ac_number not in ["AC1", "AC2"]:
        logging.error("[CONTROL ERROR] AC_NUMBER harus 'AC1' atau 'AC2'")
        return False

    payload = {
        "target": ac_number,
        "action": command,
        "AC_NUMBER": ac_number,
        "AC_COMMAND": command
    }
    if temp_val is not None:
        payload["temp"] = temp_val
    elif "TEMP" in command:
        m = re.match(r"^TEMP\s+(\d+)$", command)
        if m:
            payload["action"] = "SET_TEMP"
            payload["temp"] = int(m.group(1))

    payload_json = json.dumps(payload)
    result = client.publish(AC_COMMAND_TOPIC, payload_json)

    is_success = (result.rc == mqtt.MQTT_ERR_SUCCESS) if hasattr(result, "rc") else True
    if is_success:
        logging.info(f"[CONTROL SUCCESS] Terkirim ke '{AC_COMMAND_TOPIC}': {payload_json}")
        return True
    else:
        logging.error(f"[CONTROL FAILED] Gagal mengirim MQTT command. Result code: {getattr(result, 'rc', result)}")
        return False


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("[MQTT] Terhubung ke Local Broker (localhost)")
        client.subscribe(MQTT_TOPIC)
        logging.info(f"[MQTT] Subscribed ke topic: {MQTT_TOPIC}")
    else:
        logging.error(f"[MQTT ERROR] Gagal konek ke Broker, rc={rc}")


def on_message(client, userdata, msg):
    try:
        # Abaikan pesan command agar tidak memproses balik perintah sendiri
        if msg.topic == AC_COMMAND_TOPIC or msg.topic.endswith("/command"):
            return

        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)

        dev_id = str(data.get("DEV_ID", "")).strip().upper()
        if not dev_id:
            return

        # 1. Edge Filtering berdasarkan Whitelist
        with DEVICE_REGISTRY_LOCK:
            is_allowed = dev_id in WHITELIST_DEVICES or dev_id in DEVICE_REGISTRY

        if not is_allowed:
            logging.warning(f"[FILTER BLOCK] Perangkat {dev_id} tidak ada di Whitelist Hub. Data diabaikan.")
            
            # Auto-report unapproved/new device to HubGate V5 (heartbeat every 5s while live)
            last_reported = REPORTED_UNAPPROVED_MACS.get(dev_id, 0)
            if time.time() - last_reported >= 5:
                REPORTED_UNAPPROVED_MACS[dev_id] = time.time()
                try:
                    unapproved_payload = {
                        "HUB_NAME": data.get("HUB_NAME", HUB_ID),
                        "DEV_ID": dev_id,
                        "DEV_NAME": data.get("DEV_NAME", dev_id),
                        "DEV_TYPE": data.get("DEV_TYPE", "TS")
                    }
                    resp = requests.post(
                        SERVER_UNAPPROVED_URL,
                        json=unapproved_payload,
                        headers=get_hub_headers(),
                        verify=TLS_CERT_PATH,
                        timeout=5
                    )
                    logging.info(f"[UNAPPROVED REPORTED] Perangkat baru {dev_id} dilaporkan ke Server (HTTP {resp.status_code})")
                except Exception as e:
                    logging.warning(f"[UNAPPROVED REPORT ERROR] Gagal melaporkan {dev_id}: {e}")
            return

        # 2. Forward Telemetri ke Central Server FastAPI
        forward_success = False
        try:
            response = requests.post(
                SERVER_URL,
                json=data,
                headers=get_hub_headers(),
                verify=TLS_CERT_PATH,
                timeout=5
            )

            if response.status_code in [200, 201]:
                forward_success = True
                logging.info(f"[POST SUCCESS] Telemetri {data.get('DEV_NAME')} ({dev_id}) berhasil diteruskan ke Server.")
            else:
                logging.warning(f"[POST FAILED] Server merespon HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logging.warning(f"[FORWARD FAILED] Kendala saat mengirim telemetri ke backend: {e}")

        # 3. Offline Cache: Jika direct forward gagal, simpan ke cache SQLite WAL
        if not forward_success:
            enqueue_pending_telemetry(data)

    except json.JSONDecodeError:
        logging.error("[PARSER ERROR] Payload MQTT bukan format JSON valid.")
    except Exception as e:
        logging.error(f"[FORWARD ERROR] Kendala saat memproses telemetri: {e}")


def cli_control_loop(client):
    """Menu Interaktif Terminal Hub untuk Mengontrol AC secara Live."""
    time.sleep(2)
    print("\n" + "="*55)
    print("      KONTROL AC INTERAKTIF - HUBGATE V5")
    print("="*55)
    print("Contoh Perintah CLI:")
    print("  AC1 ON        -> Menyalakan AC 1")
    print("  AC1 OFF       -> Mematikan AC 1")
    print("  AC1 TEMP 20   -> Atur Suhu AC 1 ke 20 °C")
    print("  AC2 ON        -> Menyalakan AC 2")
    print("  exit          -> Keluar dari CLI")
    print("="*55 + "\n")

    while True:
        try:
            cmd_input = input("AC-Control> ").strip()
            if not cmd_input:
                continue

            if cmd_input.lower() in ["exit", "quit"]:
                print("Keluar dari terminal kontrol AC...")
                break

            parts = cmd_input.split(maxsplit=1)
            if len(parts) < 2:
                print("[ERROR] Format perintah salah! Gunakan format: AC1 ON atau AC1 TEMP 20")
                continue

            ac_num = parts[0]
            action = parts[1]

            send_ac_command(client, ac_num, action)

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            print(f"Error CLI: {e}")


def poll_commands_batch(client, commands_url: str = None) -> int:
    """
    Polls commands from central server, resolves downlink topic dynamically,
    publishes to MQTT broker, and marks delivered.
    Returns the number of successfully delivered commands.
    """
    url = commands_url or SERVER_COMMANDS_URL
    try:
        response = requests.get(
            url,
            headers=get_hub_headers(),
            verify=TLS_CERT_PATH,
            timeout=5
        )
    except Exception as e:
        logging.error(f"[POLL COMMAND ERROR] Failed to fetch commands: {e}")
        return 0

    if response.status_code != 200:
        logging.warning(f"[POLL COMMAND WARN] Server HTTP {response.status_code}: {response.text}")
        return 0

    commands = response.json()
    delivered_count = 0

    for cmd in commands:
        command_id = cmd.get("command_id")
        dev_id = str(cmd.get("dev_id", "")).strip().upper()
        raw_payload = cmd.get("payload")

        if not command_id or raw_payload is None:
            continue

        if isinstance(raw_payload, str):
            try:
                payload_dict = json.loads(raw_payload)
            except json.JSONDecodeError:
                logging.error(f"[POLL COMMAND JSON ERR] Payload for {command_id} is not valid JSON string.")
                continue
        elif isinstance(raw_payload, dict):
            payload_dict = raw_payload
        else:
            payload_dict = {}

        # Resolve topic dynamically
        topic = derive_command_topic(dev_id, payload_dict)
        dev_type = topic.split("/")[1] if "/" in topic else "ats"

        # Validate payload by dev_type
        is_valid = True
        err_msg = ""
        if dev_type == "ac":
            is_valid, err_msg = validate_ac_payload(payload_dict)
        elif dev_type == "ats":
            is_valid, err_msg = validate_ats_payload(payload_dict)

        if not is_valid:
            logging.error(f"[POLL COMMAND INVALID] Command {command_id} validation failed for {dev_type}: {err_msg}")
            continue

        # Publish to resolved MQTT topic
        payload_json = json.dumps(payload_dict)
        result = client.publish(topic, payload_json)

        # Check publish success
        if hasattr(result, "rc") and isinstance(result.rc, int) and result.rc == mqtt.MQTT_ERR_SUCCESS:
            is_published = True
        elif hasattr(result, "is_published"):
            is_published = result.is_published() if callable(result.is_published) else bool(result.is_published)
        elif hasattr(result, "rc"):
            is_published = (result.rc == mqtt.MQTT_ERR_SUCCESS)
        else:
            is_published = True

        if is_published:
            logging.info(f"[POLL COMMAND DISPATCHED] Published command {command_id} to '{topic}': {payload_json}")

            # Acknowledge delivery to central server
            ack_url = f"{url}/{command_id}/delivered"
            try:
                ack_res = requests.post(
                    ack_url,
                    headers=get_hub_headers(),
                    verify=TLS_CERT_PATH,
                    timeout=5
                )
                if ack_res.status_code == 200:
                    logging.info(f"[POLL COMMAND ACK] Acknowledged delivery for command {command_id}")
                    delivered_count += 1
                else:
                    logging.error(f"[POLL COMMAND ACK FAIL] Server HTTP {ack_res.status_code} on ACK: {ack_res.text}")
            except Exception as ack_err:
                logging.error(f"[POLL COMMAND ACK ERR] Failed to call /delivered: {ack_err}")
        else:
            logging.error(f"[POLL COMMAND PUB FAIL] MQTT broker did not ack publish for command {command_id}")

    return delivered_count


def poll_commands(client):
    """Secara berkala mem-poll command dari central server dan menyebarkannya ke broker lokal."""
    logging.info("[POLL] Command polling background thread started.")
    while True:
        try:
            poll_commands_batch(client)
        except Exception as e:
            logging.error(f"[POLL COMMAND EXCEPTION] Error in poll_commands: {e}")

        time.sleep(2)


def verify_tls_cert_file():
    """Validates existence and readability of TLS_CERT_PATH if configured."""
    if TLS_CERT_PATH and os.path.exists(TLS_CERT_PATH):
        if os.path.getsize(TLS_CERT_PATH) == 0:
            logging.warning(f"[SECURITY WARNING] TLS certificate '{TLS_CERT_PATH}' is empty (0 bytes).")
        else:
            logging.info(f"[SECURITY] Strict TLS certificate pinned to '{TLS_CERT_PATH}'.")
    elif TLS_CERT_PATH:
        logging.warning(f"[SECURITY WARNING] TLS certificate not found at '{TLS_CERT_PATH}'.")


def main():
    logging.info("=== Service Raspberry Pi Hub Gate V5 Diaktifkan ===")

    # Inisialisasi Database SQLite WAL Cache
    init_db()

    # Validasi file sertifikat TLS jika ada
    verify_tls_cert_file()

    # 1. Jalankan Thread Sync Whitelist di Background
    sync_thread = threading.Thread(target=sync_whitelist, daemon=True)
    sync_thread.start()

    # 2. Jalankan Thread Replay Backlog Cache di Background
    replay_thread = threading.Thread(target=replay_backlog_thread, daemon=True)
    replay_thread.start()

    # 3. Inisialisasi MQTT Client with CallbackAPIVersion.VERSION1
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"HubGateway_{HUB_ID}")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    # 4. Jalankan Thread Poll Commands di Background
    poll_thread = threading.Thread(target=poll_commands, args=(client,), daemon=True)
    poll_thread.start()

    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
    except Exception as e:
        logging.error(f"[MQTT FATAL] Gagal terhubung ke Broker lokal: {e}")
        sys.exit(1)

    # 5. Jalankan MQTT Loop di Thread Terpisah
    client.loop_start()

    # 6. Jalankan CLI Interaktif di Thread Utama atau Headless Loop
    is_interactive = "--interactive" in sys.argv or sys.stdin.isatty()
    try:
        if is_interactive:
            cli_control_loop(client)
        else:
            logging.info("Running in headless mode. Daemon active.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Mematikan service Hub...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

