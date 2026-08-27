# test_milestone1.py
import os
import sys
import uuid
import logging
from datetime import datetime, UTC

# Konfigurasi environment agar menggunakan SQLite untuk testing
os.environ["DATABASE_URL"] = "sqlite:///./test_hubgatev5.db"

# Atur logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Bersihkan database test jika ada
if os.path.exists("./test_hubgatev5.db"):
    try:
        os.remove("./test_hubgatev5.db")
    except Exception as e:
        logging.warning(f"Tidak dapat menghapus database lama: {e}")

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Inisialisasi engine SQLite test
test_engine = create_engine("sqlite:///./test_hubgatev5.db", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=test_engine)

@pytest.fixture(scope="module", autouse=True)
def setup_and_migrate_db():
    setup_legacy_database()
    run_migration_and_init()
    run_backfill()
    yield
    test_engine.dispose()
    if os.path.exists("./test_hubgatev5.db"):
        try:
            os.remove("./test_hubgatev5.db")
        except Exception:
            pass

def setup_legacy_database():
    logging.info("--- LANGKAH 1: Setup database legacy dengan skema lama ---")
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS data_table;"))
        conn.execute(text("DROP TABLE IF EXISTS temperature_data;"))
        conn.execute(text("DROP TABLE IF EXISTS ats_data;"))
        conn.execute(text("DROP TABLE IF EXISTS pending_commands;"))
        conn.execute(text("DROP TABLE IF EXISTS device_threshold_config;"))
        conn.execute(text("DROP TABLE IF EXISTS event_log;"))
        conn.execute(text("DROP TABLE IF EXISTS dev_table;"))
        conn.execute(text("DROP TABLE IF EXISTS rooms;"))
        conn.execute(text("DROP TABLE IF EXISTS hub_table;"))
        conn.execute(text("DROP TABLE IF EXISTS sessions;"))
        conn.execute(text("DROP TABLE IF EXISTS login_attempts;"))
        conn.execute(text("DROP TABLE IF EXISTS users;"))
        # Buat hub_table
        conn.execute(text("""
            CREATE TABLE hub_table (
                hub_id VARCHAR PRIMARY KEY,
                hub_name VARCHAR NOT NULL,
                hub_key VARCHAR NOT NULL,
                room VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP
            );
        """))
        
        # Buat dev_table lama dengan kolom hub_name (bukan hub_id)
        conn.execute(text("""
            CREATE TABLE dev_table (
                dev_id VARCHAR PRIMARY KEY,
                dev_name VARCHAR,
                dev_type VARCHAR,
                hub_name VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP
            );
        """))
        
        # Buat data_table lama
        conn.execute(text("""
            CREATE TABLE data_table (
                data_id VARCHAR PRIMARY KEY,
                dev_id VARCHAR,
                dev_name VARCHAR,
                timestamp TIMESTAMP,
                payload JSON
            );
        """))
        
        # Seed Hub
        conn.execute(text("""
            INSERT INTO hub_table (hub_id, hub_name, hub_key, room, is_active, created_at)
            VALUES ('RASPI_HUB_01', 'Default Edge Hub V5', 'rahasia_hub_01_xyz', 'Room A', 1, :now);
        """), {"now": datetime.now(UTC)})
        
        # Seed Devices
        conn.execute(text("""
            INSERT INTO dev_table (dev_id, dev_name, dev_type, hub_name, is_active, created_at)
            VALUES ('DEV_TS_01', 'Temp Sensor', 'TS', 'RASPI_HUB_01', 1, :now);
        """), {"now": datetime.now(UTC)})
        conn.execute(text("""
            INSERT INTO dev_table (dev_id, dev_name, dev_type, hub_name, is_active, created_at)
            VALUES ('DEV_ATS_01', 'ATS Switch', 'ATS', 'RASPI_HUB_01', 1, :now);
        """), {"now": datetime.now(UTC)})
        
        # Seed Telemetry Data
        # 1. TS Data
        conn.execute(text("""
            INSERT INTO data_table (data_id, dev_id, dev_name, timestamp, payload)
            VALUES (:id, 'DEV_TS_01', 'Temp Sensor', :ts, :payload);
        """), {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(UTC),
            "payload": '{"DEV_TYPE": "TS", "HUB_NAME": "RASPI_HUB_01", "DEV_ID": "DEV_TS_01", "DEV_NAME": "Temp Sensor", "TEMP": 28.5, "HUMID": 60.2}'
        })
        
        # 2. ATS Data (1st status: auto)
        ats_id_1 = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO data_table (data_id, dev_id, dev_name, timestamp, payload)
            VALUES (:id, 'DEV_ATS_01', 'ATS Switch', :ts, :payload);
        """), {
            "id": ats_id_1,
            "ts": datetime.now(UTC),
            "payload": '{"DEV_TYPE": "ATS", "HUB_NAME": "RASPI_HUB_01", "DEV_ID": "DEV_ATS_01", "DEV_NAME": "ATS Switch", "STATE": "auto", "PLN": 220.0, "GENSET": 0.0, "AKI": 12.5, "REM_HOUR": 10.0, "REM_MIN": 5.0, "REM_SEC": 0.0, "AUTO_MODE": true}'
        })
        
        # 3. ATS Data (2nd status: manual, 1 second later)
        ats_id_2 = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO data_table (data_id, dev_id, dev_name, timestamp, payload)
            VALUES (:id, 'DEV_ATS_01', 'ATS Switch', :ts, :payload);
        """), {
            "id": ats_id_2,
            "ts": datetime.now(UTC),
            "payload": '{"DEV_TYPE": "ATS", "HUB_NAME": "RASPI_HUB_01", "DEV_ID": "DEV_ATS_01", "DEV_NAME": "ATS Switch", "STATE": "manual", "PLN": 220.0, "GENSET": 0.0, "AKI": 12.4, "REM_HOUR": 9.0, "REM_MIN": 4.0, "REM_SEC": 0.0, "AUTO_MODE": false}'
        })

    logging.info("Setup database legacy selesai.")

def run_migration_and_init():
    logging.info("--- LANGKAH 2: Menjalankan init_sqlv5.py ---")
    import init_sqlv5
    init_sqlv5.init_db(test_engine)
    
    # Inspeksi kolom dev_table pasca migrasi
    inspector = inspect(test_engine)
    columns = [col["name"] for col in inspector.get_columns("dev_table")]
    logging.info(f"Kolom dev_table sekarang: {columns}")
    assert "hub_id" in columns, "KOLOM hub_id HARUS ADA DI dev_table!"
    assert "hub_name" not in columns, "KOLOM hub_name TIDAK BOLEH ADA DI dev_table!"
    
    # Pastikan data dev_table masih ada dan terhubung dengan hub
    with test_engine.connect() as conn:
        res = conn.execute(text("SELECT hub_id FROM dev_table WHERE dev_id = 'DEV_TS_01';")).scalar()
        logging.info(f"dev_table.hub_id untuk DEV_TS_01: {res}")
        assert res == "RASPI_HUB_01", "Data hub_id harus tetap bernilai 'RASPI_HUB_01'"

def run_backfill():
    logging.info("--- LANGKAH 3: Menjalankan backfillv5.py ---")
    import backfillv5
    backfillv5.backfill(TestSessionLocal)

def test_pydantic_validation():
    logging.info("--- LANGKAH 4: Menguji validasi Pydantic ---")
    from schemasv5 import ATSCommand
    
    # 1. Validasi minimal satu field harus diisi
    try:
        ATSCommand.model_validate({})
        assert False, "Pydantic harus menolak jika input kosong!"
    except Exception as e:
        logging.info(f"Validasi input kosong berhasil ditolak: {e}")
        
    # 2. Validasi start_genset='on' dengan mode last known = manual
    # Kita menggunakan DB session test dengan dev_id = 'DEV_ATS_01'
    # Karena records di DB kita diseed di mana data paling akhir memiliki AUTO_MODE = false (manual), maka start_genset='on' harus BERHASIL.
    db = TestSessionLocal()
    try:
        cmd = ATSCommand.model_validate(
            {"start_genset": "on"},
            context={"db": db, "dev_id": "DEV_ATS_01"}
        )
        logging.info(f"Validasi start_genset='on' saat last known mode manual BERHASIL: {cmd}")
    except Exception as e:
        assert False, f"Harusnya berhasil divalidasi karena last known mode manual, tapi gagal: {e}"
        
    # 3. Validasi start_genset='on' ketika last known mode = auto
    # Kita buat device baru 'DEV_ATS_AUTO' yang telemetri terakhirnya auto mode.
    from modelsv5 import ats_data, dev_table
    
    new_dev = dev_table(
        dev_id="DEV_ATS_AUTO",
        dev_name="ATS Auto Device",
        dev_type="ATS",
        hub_id="RASPI_HUB_01",
        is_active=True
    )
    db.add(new_dev)
    db.commit()
    
    new_ats_telemetry = ats_data(
        data_id=str(uuid.uuid4()),
        dev_id="DEV_ATS_AUTO",
        timestamp=datetime.now(UTC),
        state="auto",
        pln=220.0,
        genset=0.0,
        aki=12.5,
        rem_hour=0.0,
        rem_min=0.0,
        rem_sec=0.0,
        auto_mode=True,
        emergency=False
    )
    db.add(new_ats_telemetry)
    db.commit()
    
    try:
        ATSCommand.model_validate(
            {"start_genset": "on"},
            context={"db": db, "dev_id": "DEV_ATS_AUTO"}
        )
        assert False, "Harusnya gagal divalidasi karena last known mode adalah auto!"
    except Exception as e:
        logging.info(f"Validasi start_genset='on' saat last known mode auto BERHASIL DITOLAK: {e}")

    # 4. Validasi start_genset='on' ketika TIDAK ADA record telemetri (fail-closed)
    try:
        ATSCommand.model_validate(
            {"start_genset": "on"},
            context={"db": db, "dev_id": "DEV_ATS_NO_RECORD"}
        )
        assert False, "Harusnya gagal divalidasi karena tidak ada record telemetri (fail-closed)!"
    except Exception as e:
        logging.info(f"Validasi start_genset='on' saat tidak ada record telemetri BERHASIL DITOLAK (fail-closed): {e}")
        
    db.close()

if __name__ == "__main__":
    try:
        setup_legacy_database()
        run_migration_and_init()
        run_backfill()
        test_pydantic_validation()
        logging.info("--- SEMUA PENGUJIAN MILESTONE 1 BERHASIL! ---")
    finally:
        # Dispose engine untuk melepaskan file lock
        test_engine.dispose()
        
        # Dapatkan engine dari databasev5 dan dispose juga
        from databasev5 import engine as db_engine
        db_engine.dispose()
        
        # Bersihkan database test di akhir
        if os.path.exists("./test_hubgatev5.db"):
            try:
                os.remove("./test_hubgatev5.db")
                logging.info("Database test berhasil dibersihkan.")
            except Exception as e:
                logging.warning(f"Gagal menghapus database test di akhir: {e}")
