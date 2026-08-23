# Database v.5
# Membuat koneksi dengan database PostgreSQL / SQLite & Session Generator untuk FastAPI

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

import logging
load_dotenv()

# 1. Ambil URL dari .env (fallback ke SQLite lokal jika variabel .env tidak ditemukan)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hubgatev5.db")
if DATABASE_URL.startswith("sqlite"):
    logging.warning(f"DATABASE_URL is not set or points to SQLite. Using fallback SQLite database: {DATABASE_URL}")

# 2. Konfigurasi khusus jika menggunakan SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 3. Inisialisasi Engine
engine = create_engine(
    DATABASE_URL,
    echo=False,          # Ubah ke True jika ingin memantau query SQL mentah di terminal
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