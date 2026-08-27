import os
import paramiko

host = os.getenv("PI_HOST", "10.33.36.81")
user = os.getenv("PI_USER", "hubadmin")
password = os.getenv("PI_PASSWORD") or os.getenv("SSH_PASSWORD")
if not password:
    raise SystemExit("PI_PASSWORD env required. No hardcoded live secret.")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username=user, password=password)

service_file = """[Unit]
Description=HubBrain V5 Edge Daemon
After=network.target mosquitto.service

[Service]
Type=simple
User=hubadmin
WorkingDirectory=/home/hubadmin/hub
ExecStart=/home/hubadmin/venv/bin/python main.py
Restart=always
RestartSec=3
EnvironmentFile=/home/hubadmin/hub/.env

[Install]
WantedBy=multi-user.target
"""

print("[*] Installing hubbrain.service on Raspberry Pi...")
stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | sudo -S tee /etc/systemd/system/hubbrain.service > /dev/null")
stdin.write(service_file)
stdin.channel.shutdown_write()
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | sudo -S systemctl daemon-reload && echo '{password}' | sudo -S systemctl enable --now hubbrain.service")
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command("systemctl status hubbrain.service --no-pager")
print(stdout.read().decode())
ssh.close()
print("=== HUBBRAIN SERVICE INSTALLED & STARTED PERSISTENTLY ===")
