#!/usr/bin/env python3
"""
tools/run_pi_backup.py
Automated remote execution and off-device transfer for Raspberry Pi Backup Gate (Milestone 9 / Step 2).
"""

import os
import sys
import argparse
import hashlib
import paramiko
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Automate remote Raspberry Pi backup and off-device download")
    parser.add_argument("--host", default=os.getenv("PI_HOST", "10.33.36.81"), help="Raspberry Pi IP address (env PI_HOST)")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--user", default=os.getenv("PI_USER", "hubadmin"), help="SSH username (env PI_USER)")
    parser.add_argument("--password", default=None, help="SSH password (env PI_PASSWORD, required)")
    parser.add_argument("--local-dir", default="./pi_backups", help="Local directory to store downloaded backups")
    parser.add_argument("--app-dir", default="/home/hubadmin", help="Path to repo/app on the Pi")
    args = parser.parse_args()

    local_backup_dir = Path(args.local_dir).resolve()
    local_backup_dir.mkdir(parents=True, exist_ok=True)

    print("====================================================================")
    print("      Raspberry Pi Edge Gateway - Remote Backup Execution Tool      ")
    print("====================================================================")
    password = args.password or os.getenv("PI_PASSWORD") or os.getenv("SSH_PASSWORD")
    if not password:
        parser.error("PI_PASSWORD env required (or --password). No hardcoded live secret.")
    print(f"Connecting to {args.user}@{args.host}:{args.port}...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(args.host, port=args.port, username=args.user, password=password, timeout=10)
        print("[+] SSH connection established successfully!")
    except Exception as e:
        print(f"[!] Failed to connect to Raspberry Pi: {e}")
        sys.exit(1)

    sftp = ssh.open_sftp()

    # Step 1: Upload the latest backup_hub.sh script to /tmp/backup_hub.sh
    local_script_path = Path(__file__).resolve().parent / "backup_hub.sh"
    remote_script_path = "/tmp/backup_hub.sh"
    print(f"[*] Uploading backup script to {remote_script_path} on the Pi...")
    sftp.put(str(local_script_path), remote_script_path)

    # Step 2: Make executable and run with sudo
    cmd = f"chmod +x {remote_script_path} && echo {password} | sudo -S bash {remote_script_path} --out-dir /home/{args.user}/backups --app-dir {args.app_dir}"
    print(f"[*] Executing backup script remotely on {args.host}...")
    
    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    out_lines = []
    for line in stdout:
        print(line, end="")
        out_lines.append(line)
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print(f"[!] Remote backup execution failed with exit code: {exit_status}")
        err = stderr.read().decode()
        if err:
            print(f"Stderr:\n{err}")
        sys.exit(1)

    # Step 3: Find the newest archive and sha256 in /home/hubadmin/backups/
    remote_backup_dir = f"/home/{args.user}/backups"
    files = sftp.listdir(remote_backup_dir)
    tar_files = sorted([f for f in files if f.startswith("hubbrain_backup_") and f.endswith(".tar.gz")])
    if not tar_files:
        print(f"[!] No backup tarball found in {remote_backup_dir}")
        sys.exit(1)

    latest_tar = tar_files[-1]
    latest_sha = f"{latest_tar}.sha256"
    print(f"\n[*] Latest backup detected: {latest_tar}")

    # Step 4: Download both files off-device
    local_tar_path = local_backup_dir / latest_tar
    local_sha_path = local_backup_dir / latest_sha

    print(f"[*] Downloading {latest_tar} to {local_tar_path}...")
    sftp.get(f"{remote_backup_dir}/{latest_tar}", str(local_tar_path))

    print(f"[*] Downloading {latest_sha} to {local_sha_path}...")
    sftp.get(f"{remote_backup_dir}/{latest_sha}", str(local_sha_path))

    sftp.close()
    ssh.close()

    # Step 5: Local SHA256 integrity verification
    print("\n[*] Performing local SHA256 checksum verification...")
    hasher = hashlib.sha256()
    with open(local_tar_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    local_sha256 = hasher.hexdigest()

    with open(local_sha_path, "r", encoding="utf-8") as f:
        remote_sha256_content = f.read().strip()
        remote_sha256 = remote_sha256_content.split()[0]

    tar_size = local_tar_path.stat().st_size
    print(f"  Local File:   {local_tar_path}")
    print(f"  Size:         {tar_size:,} bytes")
    print(f"  Local SHA:    {local_sha256}")
    print(f"  Remote SHA:   {remote_sha256}")

    if local_sha256.lower() == remote_sha256.lower() and tar_size > 0:
        print("\n====================================================================")
        print(" [PASS] STEP 2 BACKUP GATE COMPLETE: ARCHIVE VERIFIED OFF-DEVICE!   ")
        print("====================================================================")
        print(f"Archive safely stored at: {local_tar_path}")
        return 0
    else:
        print("\n[FAIL] Checksum mismatch or empty file!")
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main() or 0)
