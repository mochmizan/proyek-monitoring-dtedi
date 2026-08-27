import os
import paramiko
host = os.getenv("PI_HOST", "10.33.36.81")
user = os.getenv("PI_USER", "hubadmin")
password = os.getenv("PI_PASSWORD") or os.getenv("SSH_PASSWORD")
if not password:
    raise SystemExit("PI_PASSWORD env required. No hardcoded live secret.")
mqtt_pass = os.getenv("MQTT_PASS")
if not mqtt_pass:
    raise SystemExit("MQTT_PASS env required. No hardcoded live secret.")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password)
cmd = f"timeout 8 mosquitto_sub -v -t 'hs109rs/#' -u hubadmin -P {mqtt_pass}"
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode()
err = stderr.read().decode()
print("Mosquitto Output:\n", out if out else "(No packets received in 8s)")
if err:
    print("Mosquitto Stderr:\n", err)

# Also check Wi-Fi AP clients on the Pi
stdin, stdout, stderr = ssh.exec_command("iw dev wlan0 station dump; arp -a")
print("\nConnected Wi-Fi / ARP Clients on Pi:\n", stdout.read().decode())
ssh.close()
