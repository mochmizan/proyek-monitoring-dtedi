import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("10.33.36.81", username="hubadmin", password="hubadmin")

service_file = """[Unit]
Description=HubBrain V5 Edge Daemon
After=network.target mosquitto.service

[Service]
Type=simple
User=hubadmin
WorkingDirectory=/home/hubadmin/HUBV5/V5
ExecStart=/home/hubadmin/venv/bin/python main.py
Restart=always
RestartSec=3
EnvironmentFile=/home/hubadmin/HUBV5/V5/.env

[Install]
WantedBy=multi-user.target
"""

print("[*] Installing hubbrain.service on Raspberry Pi...")
stdin, stdout, stderr = ssh.exec_command("echo 'hubadmin' | sudo -S tee /etc/systemd/system/hubbrain.service > /dev/null")
stdin.write(service_file)
stdin.channel.shutdown_write()
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command("echo 'hubadmin' | sudo -S systemctl daemon-reload && echo 'hubadmin' | sudo -S systemctl enable --now hubbrain.service")
stdout.channel.recv_exit_status()

stdin, stdout, stderr = ssh.exec_command("systemctl status hubbrain.service --no-pager")
print(stdout.read().decode())
ssh.close()
print("=== HUBBRAIN SERVICE INSTALLED & STARTED PERSISTENTLY ===")
