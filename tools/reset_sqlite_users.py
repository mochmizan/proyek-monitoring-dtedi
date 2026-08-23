import sqlite3
import uuid
from argon2 import PasswordHasher

ph = PasswordHasher()
conn = sqlite3.connect('SERVERv5/v5/hubgatev5.db')
c = conn.cursor()

accounts = [
    ('admin', 'admin123', 'System Administrator', 'admin'),
    ('operator', 'operator123', 'Facilities Operator', 'operator'),
    ('viewer', 'viewer123', 'Guest Viewer', 'viewer'),
]

for uname, pwd, dname, role in accounts:
    h = ph.hash(pwd)
    exists = c.execute('SELECT id FROM users WHERE username = ?', (uname,)).fetchone()
    if exists:
        c.execute('UPDATE users SET password_hash = ?, failed_login_attempts = 0, lockout_until = NULL WHERE username = ?', (h, uname))
        print(f'[+] Updated password for {uname}')
    else:
        c.execute('INSERT INTO users (id, username, password_hash, display_name, role, failed_login_attempts, created_at) VALUES (?, ?, ?, ?, ?, 0, datetime("now"))', (str(uuid.uuid4()), uname, h, dname, role))
        print(f'[+] Created user {uname}')

# Also clear any locked login_attempts
c.execute('DELETE FROM login_attempts')
conn.commit()
print('=== USERS CONFIGURED SUCCESSFULLY ===')
for row in c.execute('SELECT username, role FROM users').fetchall():
    print(' ', row)
conn.close()
