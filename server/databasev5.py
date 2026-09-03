# Database v.5
# Membuat koneksi dengan database PostgreSQL / SQLite & Session Generator untuk FastAPI

import os
import sqlite3
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# 1. Ambil URL dari .env (fallback ke SQLite lokal jika variabel .env tidak ditemukan)
# Fail-fast: DATABASE_URL must be explicitly set when ENV=prod
if not os.getenv("DATABASE_URL") and os.getenv("ENV") == "prod":
    raise RuntimeError("DATABASE_URL must be set when ENV=prod — refusing to start with SQLite fallback")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hubgatev5.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")
DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

if IS_SQLITE:
    logging.warning(f"DATABASE_URL is not set or points to SQLite. Using fallback SQLite database: {DATABASE_URL}")
    if os.getenv("ENV") == "prod":
        logging.warning("WARNING: Running with SQLite fallback while ENV=prod — DB_ECHO and fail-fast checks active")


def get_engine_kwargs(database_url: str = DATABASE_URL) -> dict:
    """Mengembalikan konfigurasi engine kwargs yang aman berdasarkan dialek database."""
    echo = os.getenv("DB_ECHO", "false").lower() == "true"
    if database_url.startswith("sqlite"):
        connect_args = {
            "check_same_thread": False,
            "timeout": 10.0,
        }
        return {
            "echo": echo,
            "connect_args": connect_args,
            "pool_pre_ping": True,
        }
    else:
        # PostgreSQL Configuration & Connection Pool Guard
        statement_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000"))
        connect_args = {
            "options": f"-c statement_timeout={statement_timeout_ms}"
        }
        pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))

        return {
            "echo": echo,
            "connect_args": connect_args,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": True,
        }


# 2. Konfigurasi connect_args & pool berdasarkan dialek database
engine_kwargs = get_engine_kwargs(DATABASE_URL)
connect_args = engine_kwargs.get("connect_args", {})

# 3. Inisialisasi Engine
engine = create_engine(DATABASE_URL, **engine_kwargs)


# Listener SQLite PRAGMAs untuk mengaktifkan WAL, busy_timeout, synchronous=NORMAL, foreign_keys=ON, dan temp_store=MEMORY
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA busy_timeout = 10000;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA temp_store = MEMORY;")
            cursor.execute("PRAGMA cache_size = -8000;")
            cursor.execute("PRAGMA mmap_size = 67108864;")
        finally:
            cursor.close()


# 4. Buat Factory Session
SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine
)

# 5. [V5] Base Class untuk ORM Models (diimpor di modelsv5.py)
Base = declarative_base()


# 6. [V5] Dependency Generator untuk FastAPI (diimpor di routers & auth)
def get_db():
    """
    FastAPI dependency generator untuk SQLAlchemy Session.
    Menyediakan session per-request dengan automatic rollback saat exception dan guaranteed close.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def migrate_indexes(target_engine=None):
    """Memastikan unique & composite indexes ada di database target (additive migration)."""
    try:
        from init_sqlv5 import migrate_indexes as _migrate
        _migrate(target_engine or engine)
    except Exception as e:
        logging.warning(f"migrate_indexes skipped/failed: {e}")