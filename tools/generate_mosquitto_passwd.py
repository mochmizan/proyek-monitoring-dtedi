#!/usr/bin/env python3
"""
tools/generate_mosquitto_passwd.py
Utility script to generate Eclipse Mosquitto 2.x compatible password files
using PBKDF2-HMAC-SHA512 ($7$101$<salt>$<hash>) without requiring mosquitto_passwd binary.
"""

import argparse
import base64
import hashlib
import os
import sys


def hash_mosquitto_pbkdf2(password: str, salt: bytes = None, iterations: int = 101) -> str:
    """
    Generates a Mosquitto 2.x compatible password hash:
    $7$<iterations>$<base64_salt>$<base64_hash>
    """
    if salt is None:
        salt = os.urandom(16)
    
    key = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=64
    )
    
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(key).decode("ascii")
    
    return f"$7${iterations}${salt_b64}${key_b64}"


def set_user_password(file_path: str, username: str, password: str, append_only: bool = False):
    """
    Writes or updates username and password hash in the specified mosquitto passwd file.
    """
    hashed = hash_mosquitto_pbkdf2(password)
    new_entry = f"{username}:{hashed}\n"
    
    entries = {}
    if os.path.exists(file_path) and not append_only:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and ":" in line:
                    u, h = line.split(":", 1)
                    entries[u.strip()] = h.strip()
    
    entries[username] = hashed
    
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        for u, h in entries.items():
            f.write(f"{u}:{h}\n")
    
    print(f"[SUCCESS] Updated credentials for user '{username}' in {file_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Eclipse Mosquitto 2.x password entries.")
    parser.add_argument("--user", "-u", default="hubadmin", help="MQTT username (default: hubadmin)")
    parser.add_argument("--password", "-p", default="hubadmin_local_secret_pass_2026", help="MQTT password plain-text")
    parser.add_argument("--file", "-f", default=os.path.join("mosquitto", "config", "passwd"), help="Path to output passwd file")
    
    args = parser.parse_args()
    set_user_password(args.file, args.user, args.password)


if __name__ == "__main__":
    main()
