import sqlite3

def purge_dummy():
    db_paths = [
        'SERVERv5/v5/hubgatev5.db',
    ]
    
    for db_path in db_paths:
        print(f"[*] Processing {db_path}...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Purge all mock telemetry and logs
        cursor.execute("DELETE FROM temperature_data")
        cursor.execute("DELETE FROM ats_data")
        cursor.execute("DELETE FROM data_table")
        cursor.execute("DELETE FROM event_log")
        cursor.execute("DELETE FROM pending_commands")

        # 2. Empty dev_table completely (zero pre-seeding)
        cursor.execute("DELETE FROM dev_table")

        conn.commit()

        print("=== PURGE RESULTS ===")
        print("Active devices in dev_table:")
        for r in cursor.execute("SELECT dev_id, dev_name, dev_type, room_id, is_active FROM dev_table").fetchall():
            print(f"  {r}")

        print("\nTable row counts:")
        for table in ['dev_table', 'data_table', 'temperature_data', 'ats_data', 'event_log', 'pending_commands']:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")

        conn.close()

    # Clear Raspberry Pi edge_cache.db
    try:
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('10.33.36.81', port=22, username='hubadmin', password='hubadmin', timeout=10)
        stdin, stdout, stderr = ssh.exec_command('python3 -c "import sqlite3; conn = sqlite3.connect(\'/home/hubadmin/HUBV5/V5/edge_cache.db\'); conn.execute(\'DELETE FROM offline_queue\'); conn.commit(); print(\'Cleared Pi offline_queue\')"')
        print(f"[*] Pi Edge Cache: {stdout.read().decode('utf-8').strip()}")
        ssh.close()
    except Exception as e:
        print(f"[*] Pi Edge Cache clear warning: {e}")

if __name__ == '__main__':
    purge_dummy()
