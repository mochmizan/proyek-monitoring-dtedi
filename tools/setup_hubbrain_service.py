import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("10.33.36.81", username="hubadmin", password="hubadmin")

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

stdin, stdout, stderr = ssh.exec_command("echo hubadmin | sudo -S cp /tmp/hubbrain.service /etc/systemd/system/hubbrain.service && echo hubadmin | sudo -S systemctl daemon-reload && echo hubadmin | sudo -S systemctl enable --now hubbrain.service")
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command("sleep 2 && systemctl is-active hubbrain.service")
print("Status:", stdout.read().decode("ascii", errors="ignore").strip())

stdin, stdout, stderr = ssh.exec_command("journalctl -u hubbrain.service -n 15 --no-pager")
print("Logs:\n", stdout.read().decode("ascii", errors="ignore"))

ssh.close()
