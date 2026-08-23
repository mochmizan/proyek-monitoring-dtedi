import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("10.33.36.81", username="hubadmin", password="hubadmin")
cmd = "timeout 8 mosquitto_sub -v -t 'hs109rs/#' -u hubadmin -P 414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1"
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
