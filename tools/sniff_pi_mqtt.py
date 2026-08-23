import paramiko

def sniff():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('10.33.36.81', port=22, username='hubadmin', password='hubadmin', timeout=10)
    
    cmd = 'timeout 15 mosquitto_sub -h localhost -p 1883 -u hubadmin -P 414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1 -t "hs109rs/#" -v'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    print("=== LIVE PI MOSQUITTO OUTPUT (15s window) ===")
    print(out if out.strip() else "(No MQTT messages received during 15-second window)")
    if err.strip():
        print("STDERR:", err)
    
    # Also check if wlan0 AP has connected clients
    stdin, stdout, stderr = ssh.exec_command('iw dev wlan0 station dump | grep Station')
    stations = stdout.read().decode('utf-8', errors='ignore')
    print("=== CONNECTED WI-FI CLIENTS ON PI (wlan0 AP) ===")
    print(stations if stations.strip() else "(No Wi-Fi stations currently associated with AP)")

    # Check hostapd config and status
    stdin, stdout, stderr = ssh.exec_command('echo hubadmin | sudo -S grep -E "ssid|wpa_passphrase" /etc/hostapd/hostapd.conf /etc/hostapd.conf 2>/dev/null')
    print("=== PI AP SSID CONFIG ===")
    print(stdout.read().decode('utf-8', errors='ignore'))

    # Check hostapd journal for connection attempts
    stdin, stdout, stderr = ssh.exec_command('echo hubadmin | sudo -S journalctl -u hostapd -n 15 --no-pager')
    print("=== RECENT HOSTAPD LOGS ===")
    print(stdout.read().decode('utf-8', errors='ignore'))

    # Check wlan0 IP
    stdin, stdout, stderr = ssh.exec_command('ip addr show wlan0')
    ip_out = stdout.read().decode('utf-8', errors='ignore')
    print("=== PI WLAN0 INTERFACE ===")
    print(ip_out)

    # Check /api/hub/commands from the Pi
    cmd_poll = 'curl -s -H "X-Hub-ID: hs109rs-hub-01" -H "X-Hub-Key: 70999354dda0638bbbe04b2e6d26e9f6484168193cdfdbcd517bbdf608134ee4" http://localhost:8000/api/hub/commands'
    stdin, stdout, stderr = ssh.exec_command(cmd_poll)
    print("=== PI COMMAND POLL RESPONSE ===")
    print(stdout.read().decode('utf-8', errors='ignore'))

    # Also check HubBrain V5 daemon status
    stdin, stdout, stderr = ssh.exec_command('ps aux | grep main.py | grep -v grep')
    ps_out = stdout.read().decode('utf-8', errors='ignore')
    print("=== HUBBRAIN V5 DAEMON PROCESS ===")
    print(ps_out if ps_out.strip() else "(HubBrain V5 daemon not running)")
    
    ssh.close()

if __name__ == '__main__':
    sniff()
