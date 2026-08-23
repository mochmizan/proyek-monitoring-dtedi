#!/bin/bash
set -e
apt-get update -y
apt-get install -y postgresql postgresql-contrib
service postgresql start
su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\""
su - postgres -c "psql -c \"CREATE DATABASE smsb_prod OWNER postgres;\"" || true
PG_CONF=$(find /etc/postgresql -name postgresql.conf | head -n 1)
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -n 1)
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF" || true
echo "host all all 0.0.0.0/0 md5" >> "$PG_HBA" || true
service postgresql restart
echo "=== POSTGRESQL READY ==="
