# create_admin_user.py
# CLI Script untuk membuat atau memperbarui User/Admin di Database HubGate V5

import argparse
import sys
import uuid
from sqlalchemy.orm import Session

from databasev5 import SessionLocal
from modelsv5 import User
from auth import hash_password

def create_or_update_user(username: str, password_raw: str, display_name: str, role: str):
    db = None
    try:
        db = SessionLocal()
        # Normalisasi username
        normalized_username = username.strip().lower()
        
        # Cari user yang sudah ada
        user = db.query(User).filter(User.username == normalized_username).first()
        
        # Hash password menggunakan Argon2id
        hashed_pw = hash_password(password_raw)
        
        if user:
            print(f"User '{username}' sudah terdaftar. Melakukan update data...")
            user.password_hash = hashed_pw
            user.display_name = display_name
            user.role = role
            user.failed_login_attempts = 0
            user.lockout_until = None
        else:
            print(f"User '{username}' tidak ditemukan. Membuat user baru...")
            user = User(
                id=str(uuid.uuid4()),
                username=normalized_username,
                password_hash=hashed_pw,
                display_name=display_name,
                role=role,
                failed_login_attempts=0,
                lockout_until=None
            )
            db.add(user)
            
        db.commit()
        print(f"Berhasil menyimpan user: {username} ({display_name}) dengan peran '{role}'.")
    except Exception as e:
        if db:
            db.rollback()
        print(f"ERROR: Gagal menyimpan user: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if db:
            db.close()

def main():
    parser = argparse.ArgumentParser(description="Buat atau perbarui akun pengguna HubGate V5.")
    parser.add_argument("--username", required=True, help="Username unik pengguna")
    parser.add_argument("--password", required=True, help="Password plain-text pengguna")
    parser.add_argument("--display-name", required=True, help="Nama tampilan pengguna")
    parser.add_argument("--role", required=True, choices=["root", "admin", "operator", "viewer"], help="Peran pengguna (root, admin, operator, viewer)")
    
    args = parser.parse_args()
    
    create_or_update_user(
        username=args.username,
        password_raw=args.password,
        display_name=args.display_name,
        role=args.role
    )

if __name__ == "__main__":
    main()
