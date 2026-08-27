import argparse
import os
import sys
import time
import json
import paramiko

def send_command(target="AC1", action="ON", temp=24, host=None, user=None, password=None, mqtt_pass=None):
    host = host or os.getenv("PI_HOST", "10.33.36.81")
    user = user or os.getenv("PI_USER", "hubadmin")
    password = password or os.getenv("PI_PASSWORD") or os.getenv("SSH_PASSWORD")
    if not password:
        raise SystemExit("PI_PASSWORD env required (or --password). No hardcoded live secret.")
    mqtt_pass = mqtt_pass or os.getenv("MQTT_PASS")
    if not mqtt_pass:
        raise SystemExit("MQTT_PASS env required (or --mqtt-pass). No hardcoded live secret.")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=22, username=user, password=password, timeout=10)

    payload = {"target": target, "action": action}
    if action == "SET_TEMP":
        payload["temp"] = temp

    payload_str = json.dumps(payload).replace('"', '\\"')
    cmd = f'mosquitto_pub -h localhost -p 1883 -u hubadmin -P {mqtt_pass} -t "hs109rs/ac/command" -m "{payload_str}"'
    stdin, stdout, stderr = ssh.exec_command(cmd)

    print(f"[*] Dispatched command to hs109rs/ac/command: {payload}")
    time.sleep(2)

    # Sniff response
    cmd_sub = f'timeout 6 mosquitto_sub -h localhost -p 1883 -u hubadmin -P {mqtt_pass} -t "hs109rs/ac/data" -v -C 1'
    stdin, stdout, stderr = ssh.exec_command(cmd_sub)
    resp = stdout.read().decode('utf-8', errors='ignore')
    print("=== LIVE STATE AFTER COMMAND ===")
    print(resp)
    
    ssh.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send AC command via Pi (no hardcoded secrets)")
    parser.add_argument("target", nargs="?", default="AC1", help="AC target")
    parser.add_argument("action", nargs="?", default="ON", help="AC action")
    parser.add_argument("temp", nargs="?", type=int, default=24, help="Temperature for SET_TEMP")
    parser.add_argument("--host", default=os.getenv("PI_HOST", "10.33.36.81"))
    parser.add_argument("--user", default=os.getenv("PI_USER", "hubadmin"))
    parser.add_argument("--password", default=None, help="SSH password (env PI_PASSWORD)")
    parser.add_argument("--mqtt-pass", default=None, help="MQTT password (env MQTT_PASS)")
    args = parser.parse_args()
    send_command(args.target, args.action, args.temp, host=args.host, user=args.user, password=args.password, mqtt_pass=args.mqtt_pass)
