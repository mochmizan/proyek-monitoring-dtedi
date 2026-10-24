# init_sqlv5.py
# Script Inisialisasi Tabel Database HubGate V5 & Seeding Default Hub

import logging
import os
from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

# 1. Load environment variables paling awal
load_dotenv()

# 2. Import engine, Base, dan SessionLocal dari modul V5
from databasev5 import engine, SessionLocal
from modelsv5 import (
    Base, hub_table, dev_table, data_table, event_log,
    temperature_data, ats_data, pending_commands,
    User, UserSession, LoginAttempt,
    rooms, device_threshold_config, schedules,
    ActivityLog, Cluster, UserClusterMembership, ClusterRolePermission
)

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def migrate_dev_table_hub_name_to_hub_id(bind_engine=None):
    """Mengubah kolom hub_name di dev_table menjadi hub_id jika masih menggunakan nama lama,
    serta menambahkan foreign key constraint ke hub_table.hub_id.
    """
    target_engine = bind_engine or engine
    inspector = inspect(target_engine)
    try:
        if "dev_table" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("dev_table")]
            if "hub_name" in columns and "hub_id" not in columns:
                logging.info("Migrasi: Kolom 'hub_name' ditemukan di dev_table. Melakukan rename menjadi 'hub_id'...")
                with target_engine.begin() as conn:
                    conn.execute(text("ALTER TABLE dev_table RENAME COLUMN hub_name TO hub_id;"))
                    logging.info("Migrasi: Rename kolom hub_name ke hub_id BERHASIL.")
                    
                    if target_engine.dialect.name == "postgresql":
                        try:
                            conn.execute(text(
                                "ALTER TABLE dev_table ADD CONSTRAINT fk_dev_table_hub_id "
                                "FOREIGN KEY (hub_id) REFERENCES hub_table(hub_id);"
                            ))
                            logging.info("Migrasi: Penambahan constraint FOREIGN KEY pada dev_table BERHASIL.")
                        except Exception as e:
                            logging.warning(f"Gagal menambahkan constraint FOREIGN KEY di PostgreSQL (mungkin sudah ada): {e}")
    except Exception as e:
        logging.error(f"Gagal melakukan pemeriksaan atau migrasi kolom: {e}")
        raise

def migrate_additive_columns(bind_engine=None):
    """Melakukan additive migrations untuk kolom baru yang ditambahkan ke tabel yang sudah ada:
    - dev_table: room_id, marker_x, marker_y
    - event_log: dev_id, room_id, metric, severity, value, threshold, resolved_at
    - hub_table: last_seen, status
    """
    target_engine = bind_engine or engine
    inspector = inspect(target_engine)
    try:
        table_names = inspector.get_table_names()
        is_pg = target_engine.dialect.name == "postgresql"

        # 1. dev_table: room_id, marker_x, marker_y, last_seen, last_status
        if "dev_table" in table_names:
            dev_cols = [col["name"] for col in inspector.get_columns("dev_table")]
            ts_type = "TIMESTAMP WITH TIME ZONE" if is_pg else "TIMESTAMP"
            with target_engine.begin() as conn:
                if "room_id" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'room_id' ke dev_table...")
                    conn.execute(text("ALTER TABLE dev_table ADD COLUMN room_id VARCHAR;"))
                if "marker_x" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'marker_x' ke dev_table...")
                    conn.execute(text("ALTER TABLE dev_table ADD COLUMN marker_x FLOAT;"))
                if "marker_y" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'marker_y' ke dev_table...")
                    conn.execute(text("ALTER TABLE dev_table ADD COLUMN marker_y FLOAT;"))
                if "last_seen" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'last_seen' ke dev_table...")
                    conn.execute(text(f"ALTER TABLE dev_table ADD COLUMN last_seen {ts_type};"))
                if "last_status" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'last_status' ke dev_table...")
                    conn.execute(text("ALTER TABLE dev_table ADD COLUMN last_status VARCHAR DEFAULT 'offline';"))
                if "cluster_id" not in dev_cols:
                    logging.info("Migrasi: Menambahkan kolom 'cluster_id' ke dev_table...")
                    conn.execute(text("ALTER TABLE dev_table ADD COLUMN cluster_id VARCHAR;"))

        # 2. event_log: dev_id, room_id, metric, severity, value, threshold, resolved_at
        if "event_log" in table_names:
            event_cols = [col["name"] for col in inspector.get_columns("event_log")]
            ts_type = "TIMESTAMP WITH TIME ZONE" if is_pg else "TIMESTAMP"
            with target_engine.begin() as conn:
                if "dev_id" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'dev_id' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN dev_id VARCHAR;"))
                if "room_id" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'room_id' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN room_id VARCHAR;"))
                if "metric" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'metric' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN metric VARCHAR;"))
                if "severity" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'severity' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN severity VARCHAR;"))
                if "value" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'value' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN value FLOAT;"))
                if "threshold" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'threshold' ke event_log...")
                    conn.execute(text("ALTER TABLE event_log ADD COLUMN threshold FLOAT;"))
                if "resolved_at" not in event_cols:
                    logging.info("Migrasi: Menambahkan kolom 'resolved_at' ke event_log...")
                    conn.execute(text(f"ALTER TABLE event_log ADD COLUMN resolved_at {ts_type};"))

        # 3. hub_table: last_seen, status
        if "hub_table" in table_names:
            hub_cols = [col["name"] for col in inspector.get_columns("hub_table")]
            ts_type = "TIMESTAMP WITH TIME ZONE" if is_pg else "TIMESTAMP"
            with target_engine.begin() as conn:
                if "last_seen" not in hub_cols:
                    logging.info("Migrasi: Menambahkan kolom 'last_seen' ke hub_table...")
                    conn.execute(text(f"ALTER TABLE hub_table ADD COLUMN last_seen {ts_type};"))
                if "status" not in hub_cols:
                    logging.info("Migrasi: Menambahkan kolom 'status' ke hub_table...")
                    conn.execute(text("ALTER TABLE hub_table ADD COLUMN status VARCHAR DEFAULT 'offline';"))

        # 4. rooms: cluster_id
        if "rooms" in table_names:
            room_cols = [col["name"] for col in inspector.get_columns("rooms")]
            with target_engine.begin() as conn:
                if "cluster_id" not in room_cols:
                    logging.info("Migrasi: Menambahkan kolom 'cluster_id' ke rooms...")
                    conn.execute(text("ALTER TABLE rooms ADD COLUMN cluster_id VARCHAR;"))
    except Exception as e:
        logging.error(f"Gagal melakukan additive migration kolom: {e}")
        raise

def try_alembic_upgrade(bind_engine=None):
    """Call alembic upgrade head if alembic is present; additive fallback otherwise."""
    try:
        import alembic.config
        import alembic.command
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_ini = os.path.join(base_dir, "alembic.ini")
        if os.path.exists(alembic_ini):
            cfg = alembic.config.Config(alembic_ini)
            cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
            # Override URL to current engine URL
            target_engine = bind_engine or engine
            cfg.set_main_option("sqlalchemy.url", str(target_engine.url))
            alembic.command.upgrade(cfg, "head")
            logging.info("Alembic upgrade head BERHASIL")
            return True
    except Exception as e:
        logging.warning(f"Alembic upgrade skipped/fallback: {e}")
    return False

def migrate_indexes(bind_engine=None):
    """Ensures composite indexes exist on target tables as an additive fallback."""
    target_engine = bind_engine or engine
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    indexes_to_create = [
        ("event_log", "ix_event_log_dev_metric_ts", "CREATE INDEX IF NOT EXISTS ix_event_log_dev_metric_ts ON event_log (dev_id, metric, timestamp DESC)"),
        ("event_log", "ix_event_log_room_ts", "CREATE INDEX IF NOT EXISTS ix_event_log_room_ts ON event_log (room_id, timestamp DESC)"),
        ("event_log", "ix_event_log_dev_resolved", "CREATE INDEX IF NOT EXISTS ix_event_log_dev_resolved ON event_log (dev_id, resolved_at)"),
        ("event_log", "ix_event_log_ts_desc", "CREATE INDEX IF NOT EXISTS ix_event_log_ts_desc ON event_log (timestamp DESC)"),
        ("dev_table", "ix_dev_table_hub_id", "CREATE INDEX IF NOT EXISTS ix_dev_table_hub_id ON dev_table (hub_id)"),
        ("dev_table", "ix_dev_table_room_id", "CREATE INDEX IF NOT EXISTS ix_dev_table_room_id ON dev_table (room_id)"),
        ("dev_table", "ix_dev_table_dev_name", "CREATE INDEX IF NOT EXISTS ix_dev_table_dev_name ON dev_table (dev_name)"),
        ("pending_commands", "ix_pending_commands_hub_status_created", "CREATE INDEX IF NOT EXISTS ix_pending_commands_hub_status_created ON pending_commands (hub_id, status, created_at)"),
        ("data_table", "ix_data_table_dev_ts_desc", "CREATE INDEX IF NOT EXISTS ix_data_table_dev_ts_desc ON data_table (dev_id, timestamp DESC)"),
        ("sessions", "ix_sessions_user_expires", "CREATE INDEX IF NOT EXISTS ix_sessions_user_expires ON sessions (user_id, expires_at)"),
        ("temperature_data", "uq_temp_dev_timestamp", "CREATE UNIQUE INDEX IF NOT EXISTS uq_temp_dev_timestamp ON temperature_data (dev_id, timestamp)"),
        ("ats_data", "uq_ats_dev_timestamp", "CREATE UNIQUE INDEX IF NOT EXISTS uq_ats_dev_timestamp ON ats_data (dev_id, timestamp)"),
        ("data_table", "uq_data_dev_timestamp", "CREATE UNIQUE INDEX IF NOT EXISTS uq_data_dev_timestamp ON data_table (dev_id, timestamp)"),
    ]
    with target_engine.begin() as conn:
        for tbl, idx_name, sql in indexes_to_create:
            if tbl in existing_tables:
                try:
                    if idx_name.startswith("uq_") and target_engine.dialect.name == "sqlite":
                        conn.execute(text(f"""
                            DELETE FROM {tbl}
                            WHERE rowid NOT IN (
                                SELECT MIN(rowid)
                                FROM {tbl}
                                GROUP BY dev_id, timestamp
                            )
                        """))
                    conn.execute(text(sql))
                except Exception as e:
                    logging.warning(f"Fallback migrate_indexes could not create {idx_name}: {e}")

def init_db(bind_engine=None):
    try:
        target_engine = bind_engine or engine
        # Try alembic first (best-effort), then always ensure additive + create_all for idempotency
        try_alembic_upgrade(target_engine)
        # Jalankan migrasi kolom sebelum create_all agar kolom yang ada di-rename / ditambahkan terlebih dahulu
        migrate_dev_table_hub_name_to_hub_id(target_engine)
        migrate_additive_columns(target_engine)

        logging.info("Memulai pembuatan / verifikasi tabel V5 di database...")
        Base.metadata.create_all(bind=target_engine)
        migrate_indexes(target_engine)
        logging.info("Pembuatan tabel database V5 BERHASIL!")

        # Seeding Default Hub Pertama (Jika belum ada Hub sama sekali)
        seed_default_hub(target_engine)

    except Exception as e:
        logging.error(f"Gagal membuat tabel database: {e}")
        raise

def seed_default_hub(bind_engine=None):
    """Memastikan minimal ada 1 Hub resmi awal terdaftar di database."""
    # Fail-fast: default HUB_KEY only allowed when ENV != prod
    if os.getenv("HUB_KEY", "rahasia_hub_01_xyz") == "rahasia_hub_01_xyz" and os.getenv("ENV") == "prod":
        raise RuntimeError("HUB_KEY default 'rahasia_hub_01_xyz' is not allowed when ENV=prod — set a secure HUB_KEY")
    if os.getenv("HUB_KEY") is None and os.getenv("ENV") != "prod":
        logging.warning("HUB_KEY not set — using default 'rahasia_hub_01_xyz' (only allowed when ENV!=prod)")
    target_engine = bind_engine or engine
    if bind_engine is not None:
        CustomSession = sessionmaker(autoflush=False, autocommit=False, bind=target_engine)
        db = CustomSession()
    else:
        db = SessionLocal()
    try:
        default_hub_id = os.getenv("HUB_NAME", "RASPI_HUB_01")
        default_hub_key = os.getenv("HUB_KEY", "rahasia_hub_01_xyz")

        exist = db.get(hub_table, default_hub_id)
        if not exist:
            initial_hub = hub_table(
                hub_id=default_hub_id,
                hub_name="Default Edge Hub V5",
                hub_key=default_hub_key,
                is_active=True
            )
            db.add(initial_hub)
            db.commit()
            logging.info(f"[SEED] Default Hub '{default_hub_id}' berhasil ditambahkan ke database hubs.")
        else:
            logging.info(f"[SEED] Hub '{default_hub_id}' sudah ada di database.")

    except Exception as e:
        db.rollback()
        logging.error(f"Gagal melakukan seeding default hub: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()