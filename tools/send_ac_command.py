import sys
import time
import json
import paramiko

def send_command(target="AC1", action="ON", temp=24):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect('10.33.36.81', port=22, username='hubadmin', password='hubadmin', timeout=10)
    
    payload = {"target": target, "action": action}
    if action == "SET_TEMP":
        payload["temp"] = temp
        
    payload_str = json.dumps(payload).replace('"', '\\"')
    cmd = f'mosquitto_pub -h localhost -p 1883 -u hubadmin -P 414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1 -t "hs109rs/ac/command" -m "{payload_str}"'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    
    print(f"[*] Dispatched command to hs109rs/ac/command: {payload}")
    time.sleep(2)
    
    # Sniff response
    cmd_sub = 'timeout 6 mosquitto_sub -h localhost -p 1883 -u hubadmin -P 414d9d5949fd2a25f4860d7274c851891ed3551ef85bbf0ac57520bc9416c8e1 -t "hs109rs/ac/data" -v -C 1'
    stdin, stdout, stderr = ssh.exec_command(cmd_sub)
    resp = stdout.read().decode('utf-8', errors='ignore')
    print("=== LIVE STATE AFTER COMMAND ===")
    print(resp)
    
    ssh.close()

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "AC1"
    action = sys.argv[2] if len(sys.argv) > 2 else "ON"
    temp = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    send_command(target, action, temp)
