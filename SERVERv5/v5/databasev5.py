# Database v.5
# Membuat koneksi dengan database PostgreSQL / SQLite & Session Generator untuk FastAPI

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

import logging
load_dotenv()

# 1. Ambil URL dari .env (fallback ke SQLite lokal jika variabel .env tidak ditemukan)
# Fail-fast: DATABASE_URL must be explicitly set when ENV=prod
if not os.getenv("DATABASE_URL") and os.getenv("ENV") == "prod":
    raise RuntimeError("DATABASE_URL must be set when ENV=prod — refusing to start with SQLite fallback")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hubgatev5.db")
if DATABASE_URL.startswith("sqlite"):
    logging.warning(f"DATABASE_URL is not set or points to SQLite. Using fallback SQLite database: {DATABASE_URL}")
    if os.getenv("ENV") == "prod":
        logging.warning("WARNING: Running with SQLite fallback while ENV=prod — DB_ECHO and fail-fast checks active")

# 2. Konfigurasi khusus jika menggunakan SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 3. Inisialisasi Engine — DB_ECHO env controls SQL echo (set DB_ECHO=true to enable)
engine = create_engine(
    DATABASE_URL,
    echo=(os.getenv("DB_ECHO", "false").lower() == "true"),
    connect_args=connect_args,
    pool_pre_ping=True   # [V5] Otomatis mendeteksi & menyambung ulang jika koneksi DB terputus
)

# 4. Buat Factory Session
SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine
)

# 5. [V5] Base Class untuk ORM Models (diimpor di modelsv5.py)
Base = declarative_base()

# 6. [V5] Dependency Generator untuk FastAPI (diimpor di hubgatev5.py)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()