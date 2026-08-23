#!/usr/bin/env python3
"""
tools/deploy_pi_edge.py
Deploys updated HubBrain V5 to the Raspberry Pi, sets up .env, establishes reverse port tunnel,
and runs HubBrain edge gateway connected to the laptop's HubGate V5 server.
"""

import sys
import time
import socket
import select
import threading
import paramiko
from pathlib import Path

def reverse_forward_tunnel(server_port, remote_host, remote_port, transport):
    transport.request_port_forward('', server_port)
    while True:
        chan = transport.accept(1000)
        if chan is None:
            continue
        thr = threading.Thread(target=handler, args=(chan, remote_host, remote_port))
        thr.daemon = True
        thr.start()

def handler(chan, host, port):
    sock = socket.socket()
    try:
        sock.connect((host, port))
    except Exception as e:
        chan.close()
        return

    while True:
        r, w, x = select.select([sock, chan], [], [])
        if sock in r:
            data = sock.recv(1024)
            if len(data) == 0:
                break
            chan.send(data)
        if chan in r:
            data = chan.recv(1024)
            if len(data) == 0:
                break
            sock.send(data)
    chan.close()
    sock.close()

def main():
    host = "10.33.36.81"
    user = "hubadmin"
    password = "hubadmin"

    print("====================================================================")
    print("      SMSB Platform - Raspberry Pi HubBrain V5 Edge Deployer        ")
    print("====================================================================")
    print(f"Connecting to {user}@{host}...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=22, username=user, password=password, timeout=10)
    sftp = ssh.open_sftp()

    # Step 1: Upload latest HUBV5/V5/main.py
    local_main = Path(__file__).resolve().parent.parent / "HUBV5" / "V5" / "main.py"
    remote_dir = f"/home/{user}/HUBV5/V5"
    remote_main = f"{remote_dir}/main.py"
    remote_env = f"{remote_dir}/.env"

    print(f"[*] Uploading updated main.py to {remote_main}...")
    sftp.put(str(local_main), remote_main)

    # Step 2: Write updated .env for local staging
    staging_env_content = f"""# Local Hardware Staging .env for HubBrain V5
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TOPIC=hs109rs/#
MQTT_USER=hubadmin
MQTT_PASS=414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1
HUB_NAME=hs109rs-hub-01
HUB_KEY=70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4
ALLOW_INSECURE_DEV_KEYS=true

# Upstream endpoints directly to Laptop HubGate V5 on LAN
SERVER_URL=http://10.33.36.80:8000/api/iot
SERVER_DEVICES_URL=http://10.33.36.80:8000/api/devices
SERVER_ALERT_URL=http://10.33.36.80:8000/api/iot/unapproved
SERVER_COMMANDS_URL=http://10.33.36.80:8000/api/hub/commands

TLS_CERT_PATH=
EDGE_CACHE_DB_PATH=edge_cache.db
"""
    print(f"[*] Writing updated .env to {remote_env}...")
    with sftp.open(remote_env, "w") as f:
        f.write(staging_env_content)

    sftp.close()

    # Step 3: Restart Mosquitto Broker
    print("[*] Ensuring Mosquitto service is running on the Pi...")
    stdin, stdout, stderr = ssh.exec_command(f"echo {password} | sudo -S systemctl restart mosquitto")
    stdout.channel.recv_exit_status()

    # Step 4: Start HubBrain V5 daemon on the Pi
    print("[*] Launching HubBrain V5 edge daemon on the Pi...")
    run_cmd = f"cd {remote_dir} && /home/{user}/venv/bin/python main.py"
    stdin, stdout, stderr = ssh.exec_command(run_cmd, get_pty=True)

    print("\n--- Live HubBrain Output Stream ---")
    try:
        for line in iter(stdout.readline, ""):
            print(line, end="")
    except KeyboardInterrupt:
        print("\nStopping HubBrain...")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
