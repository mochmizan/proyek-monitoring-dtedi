import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SERVERv5', 'v5')))

import datetime
from datetime import UTC, timedelta
from databasev5 import SessionLocal
from modelsv5 import UserSession, User
from auth import create_session, verify_session

db = SessionLocal()
admin = db.query(User).filter(User.username == 'admin').first()
print('Admin:', admin.username if admin else None)
sess = create_session(db, admin.id)
print('Created Session:', sess.session_id)
print('  created_at:', repr(sess.created_at))
print('  expires_at:', repr(sess.expires_at))
try:
    u = verify_session(db, sess.session_id)
    print('Verified User:', u.username if u else None)
except Exception as e:
    print('Verify Error:', type(e), e)
db.close()
