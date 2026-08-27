import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'server', 'v5')))

os.environ['DATABASE_URL'] = 'postgresql+psycopg2://postgres:postgres@localhost:5432/smsb_prod'

from databasev5 import engine, Base, SessionLocal
import modelsv5
from modelsv5 import User, hub_table, rooms
from auth import hash_password

print('[*] Creating database schema in PostgreSQL...')
Base.metadata.create_all(engine)
db = SessionLocal()

# 1. Users (Admin, Operator, Viewer)
users_seed = [
    ('admin', 'admin123', 'System Administrator', 'admin'),
    ('operator', 'operator123', 'Facilities Operator', 'operator'),
    ('viewer', 'viewer123', 'Guest Viewer', 'viewer'),
]
for uname, pwd, dname, urole in users_seed:
    existing = db.query(User).filter(User.username == uname).first()
    if not existing:
        import uuid
        u = User(
            id=str(uuid.uuid4()),
            username=uname,
            password_hash=hash_password(pwd),
            display_name=dname,
            role=urole
        )
        db.add(u)
        print(f'  [+] Seeded user {uname} ({urole})')

# 2. Hub
if not db.get(hub_table, 'hs109rs-hub-01'):
    hub_key = os.getenv("HUB_KEY")
    if not hub_key:
        raise SystemExit("HUB_KEY env required (no hardcoded live secret).")
    hub = hub_table(
        hub_id='hs109rs-hub-01',
        hub_name='Hub hs109rs (Lab IoT)',
        hub_key=hub_key,
        room='Server Room',
        is_active=True
    )
    db.add(hub)
    print('  [+] Seeded hub hs109rs-hub-01')

# 3. Standard Rooms
rooms_data = [
    ('room-server', 'Server Room', 'hs109rs-hub-01'),
    ('room-net', 'Network Closet', 'hs109rs-hub-01'),
    ('room-battery', 'Battery Room', 'hs109rs-hub-01')
]
for r_id, r_name, h_id in rooms_data:
    if not db.get(rooms, r_id):
        r = rooms(id=r_id, name=r_name, hub_id=h_id)
        db.add(r)
        print(f'  [+] Seeded room {r_name}')

db.commit()
print('=== POSTGRESQL INITIALIZED & SEEDED (ZERO DUMMY DEVICES) ===')
db.close()
