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

sftp = ssh.open_sftp()
with sftp.open("/tmp/hubbrain.service", "w") as f:
    f.write("""[Unit]
Description=HubBrain V5 Edge Gateway
After=network.target mosquitto.service

[Service]
Type=simple
User=hubadmin
WorkingDirectory=/home/hubadmin/HUBV5/V5
ExecStart=/home/hubadmin/venv/bin/python /home/hubadmin/HUBV5/V5/main.py
Restart=always
RestartSec=3
EnvironmentFile=/home/hubadmin/HUBV5/V5/.env

[Install]
WantedBy=multi-user.target
""")
sftp.close()

stdin, stdout, stderr = ssh.exec_command(f"echo {password} | sudo -S cp /tmp/hubbrain.service /etc/systemd/system/hubbrain.service && echo {password} | sudo -S systemctl daemon-reload && echo {password} | sudo -S systemctl enable --now hubbrain.service")
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command("sleep 2 && systemctl is-active hubbrain.service")
print("Status:", stdout.read().decode("ascii", errors="ignore").strip())

stdin, stdout, stderr = ssh.exec_command("journalctl -u hubbrain.service -n 15 --no-pager")
print("Logs:\n", stdout.read().decode("ascii", errors="ignore"))

ssh.close()
