"""
Unit and Integration Tests for tools/migrate_sqlite_to_postgres.py
SMSB HubGate V5 Infrastructure Hardening (Phase 4.2)
"""

import datetime
import json
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch
import pytest

# Add tools and server to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from migrate_sqlite_to_postgres import (
    normalize_pg_dsn,
    sanitize_datetime,
    sanitize_boolean,
    sanitize_json,
    get_column_sanitizer_type,
    sanitize_row,
    get_sqlite_tables,
    get_sqlite_columns,
    resync_postgres_sequences,
    execute_migration,
)


# --- 1. DSN Normalization Tests ---

def test_normalize_pg_dsn():
    assert normalize_pg_dsn("postgresql+psycopg2://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    assert normalize_pg_dsn("postgresql+psycopg://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    assert normalize_pg_dsn("postgresql://user:pass@host:5432/db") == "postgresql://user:pass@host:5432/db"
    assert normalize_pg_dsn("") == ""
    assert normalize_pg_dsn(None) is None


# --- 2. Sanitizer Function Tests ---

def test_sanitize_datetime_iso_and_naive():
    # Naive space-separated string (typical SQLite)
    dt1 = sanitize_datetime("2026-09-02 11:43:27.746526")
    assert isinstance(dt1, datetime.datetime)
    assert dt1.tzinfo == datetime.timezone.utc
    assert dt1.year == 2026 and dt1.month == 9 and dt1.day == 2

    # ISO format with Z
    dt2 = sanitize_datetime("2026-09-02T11:43:27.746526Z")
    assert dt2.tzinfo == datetime.timezone.utc
    assert dt2.minute == 43

    # ISO format with +00:00
    dt3 = sanitize_datetime("2026-09-02T11:43:27.746526+00:00")
    assert dt3.tzinfo == datetime.timezone.utc

    # Existing datetime object
    now = datetime.datetime.now()
    dt4 = sanitize_datetime(now)
    assert dt4.tzinfo == datetime.timezone.utc

    # Timestamp float
    epoch = 1700000000.0
    dt5 = sanitize_datetime(epoch)
    assert dt5.tzinfo == datetime.timezone.utc
    assert dt5.timestamp() == epoch

    # Empty / None / invalid
    assert sanitize_datetime(None) is None
    assert sanitize_datetime("") is None
    assert sanitize_datetime("None") is None
    assert sanitize_datetime("invalid-date-string") is None


def test_sanitize_boolean():
    assert sanitize_boolean(1) is True
    assert sanitize_boolean(0) is False
    assert sanitize_boolean(1.0) is True
    assert sanitize_boolean(0.0) is False

    assert sanitize_boolean("1") is True
    assert sanitize_boolean("0") is False
    assert sanitize_boolean("true") is True
    assert sanitize_boolean("false") is False
    assert sanitize_boolean("TRUE") is True
    assert sanitize_boolean("FALSE") is False
    assert sanitize_boolean("t") is True
    assert sanitize_boolean("f") is False
    assert sanitize_boolean("yes") is True
    assert sanitize_boolean("no") is False

    assert sanitize_boolean(True) is True
    assert sanitize_boolean(False) is False
    assert sanitize_boolean(None) is None


def test_sanitize_json():
    data = {"sensor": "temp", "value": 24.5, "tags": ["ac", "rack"]}
    
    # Python dict
    res1 = sanitize_json(data)
    assert json.loads(res1) == data

    # Valid JSON string
    json_str = json.dumps(data)
    res2 = sanitize_json(json_str)
    assert json.loads(res2) == data

    # Raw string
    res3 = sanitize_json("plain string")
    assert json.loads(res3) == "plain string"

    # None and empty
    assert sanitize_json(None) is None
    assert sanitize_json("") is None
    assert sanitize_json("None") is None


# --- 3. Column Type Deduction & Row Sanitization ---

def test_get_column_sanitizer_type():
    assert get_column_sanitizer_type("timestamp", "ats_data") == "datetime"
    assert get_column_sanitizer_type("created_at", "hub_table") == "datetime"
    assert get_column_sanitizer_type("is_active", "dev_table") == "bool"
    assert get_column_sanitizer_type("auto_mode", "ats_data") == "bool"
    assert get_column_sanitizer_type("payload", "data_table") == "json"
    assert get_column_sanitizer_type("dev_id", "dev_table") == "raw"
    assert get_column_sanitizer_type("hub_name", "hub_table") == "raw"


def test_sanitize_row():
    types = ["raw", "bool", "datetime", "json"]
    raw_row = ("dev-01", 1, "2026-09-02 11:00:00", '{"temp": 25.0}')
    
    sanitized = sanitize_row(raw_row, types, wrap_psycopg_json=False)
    assert sanitized[0] == "dev-01"
    assert sanitized[1] is True
    assert isinstance(sanitized[2], datetime.datetime)
    assert sanitized[2].tzinfo == datetime.timezone.utc
    assert json.loads(sanitized[3]) == {"temp": 25.0}


# --- 4. SQLite Schema & Dry-Run Integration Tests ---

@pytest.fixture
def sample_sqlite_db():
    """Create a temporary SQLite database populated with HubGate V5 schema and test rows."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE alembic_version (
            version_num VARCHAR(32) NOT NULL PRIMARY KEY
        );
    """)
    cur.execute("INSERT INTO alembic_version VALUES ('c1a8b9f0e2d3');")

    cur.execute("""
        CREATE TABLE hub_table (
            hub_id VARCHAR PRIMARY KEY,
            hub_name VARCHAR NOT NULL,
            hub_key VARCHAR NOT NULL,
            room VARCHAR,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP,
            last_seen TIMESTAMP,
            status VARCHAR DEFAULT 'offline'
        );
    """)
    cur.execute("""
        INSERT INTO hub_table VALUES 
        ('hub-01', 'Test Hub', 'secret-key', 'Server Room', 1, '2026-09-02 10:00:00', NULL, 'online');
    """)

    cur.execute("""
        CREATE TABLE dev_table (
            dev_id VARCHAR PRIMARY KEY,
            dev_name VARCHAR,
            dev_type VARCHAR,
            hub_id VARCHAR,
            is_active BOOLEAN NOT NULL DEFAULT 0,
            created_at TIMESTAMP,
            last_seen TIMESTAMP,
            last_status VARCHAR DEFAULT 'offline',
            room_id VARCHAR,
            marker_x FLOAT,
            marker_y FLOAT
        );
    """)
    cur.execute("""
        INSERT INTO dev_table VALUES 
        ('dev-01', 'Sensor 1', 'temperature', 'hub-01', 1, '2026-09-02 10:05:00', NULL, 'online', NULL, 10.5, 20.5),
        ('dev-02', 'ATS Genset', 'ats', 'hub-01', 0, '2026-09-02 10:06:00', NULL, 'offline', NULL, NULL, NULL);
    """)

    cur.execute("""
        CREATE TABLE ats_data (
            data_id VARCHAR PRIMARY KEY,
            dev_id VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            state VARCHAR NOT NULL,
            pln FLOAT NOT NULL,
            genset FLOAT NOT NULL,
            aki FLOAT NOT NULL,
            rem_hour FLOAT NOT NULL,
            rem_min FLOAT NOT NULL,
            rem_sec FLOAT NOT NULL,
            auto_mode BOOLEAN NOT NULL,
            emergency BOOLEAN NOT NULL
        );
    """)
    cur.execute("""
        INSERT INTO ats_data VALUES 
        ('ats-01', 'dev-02', '2026-09-02 10:10:00.123456', 'PLN', 220.5, 0.0, 13.8, 0, 0, 0, 1, 0);
    """)

    cur.execute("""
        CREATE TABLE data_table (
            data_id VARCHAR PRIMARY KEY,
            dev_id VARCHAR,
            dev_name VARCHAR,
            timestamp TIMESTAMP,
            payload JSON
        );
    """)
    cur.execute("""
        INSERT INTO data_table VALUES 
        ('data-01', 'dev-01', 'Sensor 1', '2026-09-02 10:15:00', '{"temperature": 23.4, "humidity": 60.1}');
    """)

    conn.commit()
    conn.close()

    yield path

    if os.path.exists(path):
        os.remove(path)


def test_sqlite_schema_extraction(sample_sqlite_db):
    conn = sqlite3.connect(sample_sqlite_db)
    tables = get_sqlite_tables(conn)
    assert "hub_table" in tables
    assert "dev_table" in tables
    assert "ats_data" in tables
    assert "data_table" in tables
    assert "alembic_version" in tables

    hub_cols = get_sqlite_columns(conn, "hub_table")
    assert "hub_id" in hub_cols
    assert "is_active" in hub_cols
    assert "created_at" in hub_cols
    conn.close()


def test_execute_migration_dry_run(sample_sqlite_db):
    """Test that dry-run streams through tables, parses all rows, and outputs success."""
    success = execute_migration(
        sqlite_path=sample_sqlite_db,
        pg_url=None,
        batch_size=10,
        dry_run=True,
    )
    assert success is True


def test_execute_migration_missing_sqlite_file():
    """Verify execution aborts gracefully if source file does not exist."""
    success = execute_migration(
        sqlite_path="non_existent_file_12345.db",
        pg_url=None,
        dry_run=True,
    )
    assert success is False


# --- 5. Mocked PostgreSQL Ingestion & Resync Tests ---

def test_resync_postgres_sequences():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate two tables: one with sequence, one without
    mock_cursor.fetchall.return_value = [
        ("items", "id", "items_id_seq"),
        ("users", "id", None),
    ]
    mock_cursor.fetchone.return_value = (42,)

    resynced = resync_postgres_sequences(mock_conn)
    assert resynced == 1
    # Verify setval was called for items_id_seq with 42
    mock_cursor.execute.assert_any_call("SELECT setval(%s, %s, true);", ("items_id_seq", 42))


def test_execute_migration_replication_role_lifecycle(sample_sqlite_db):
    """Verify session_replication_role is set to 'replica' during load and restored to 'origin'."""
    mock_pg_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pg_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate get_pg_columns and counts matching exactly
    def cursor_execute(query, params=None):
        pass

    mock_cursor.execute = MagicMock(side_effect=cursor_execute)
    # Whenever COUNT(*) is queried, return the expected row count so parity passes
    mock_cursor.fetchone.side_effect = [(1,), (2,), (1,), (1,), (1,)]

    with patch("psycopg2.connect", return_value=mock_pg_conn):
        with patch("psycopg2.extras.execute_values"):
            with patch("migrate_sqlite_to_postgres.get_pg_columns", side_effect=lambda conn, tbl: ["hub_id", "hub_name", "hub_key", "is_active", "created_at"]):
                with patch("migrate_sqlite_to_postgres.resync_postgres_sequences", return_value=0):
                    success = execute_migration(
                        sqlite_path=sample_sqlite_db,
                        pg_url="postgresql://user:pass@127.0.0.1:5432/testdb",
                        batch_size=10,
                        dry_run=False,
                        truncate=False,
                    )

    assert success is True
    # Verify SET session_replication_role = 'replica' and 'origin' were executed
    calls = [str(call) for call in mock_cursor.execute.call_args_list]
    assert any("session_replication_role = 'replica'" in c for c in calls)
    assert any("session_replication_role = 'origin'" in c for c in calls)
    assert any("synchronous_commit = off" in c for c in calls)


def test_execute_migration_replication_role_restored_on_exception(sample_sqlite_db):
    """Verify session_replication_role is guaranteed to be restored to 'origin' even on ingestion failure."""
    mock_pg_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pg_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_pg_conn.closed = False

    # Simulate get_pg_columns raising an error to abort migration during ingestion
    with patch("psycopg2.connect", return_value=mock_pg_conn):
        with patch("migrate_sqlite_to_postgres.get_pg_columns", side_effect=RuntimeError("Simulated DB error during ingest")):
            success = execute_migration(
                sqlite_path=sample_sqlite_db,
                pg_url="postgresql://user:pass@127.0.0.1:5432/testdb",
                batch_size=10,
                dry_run=False,
                truncate=False,
            )

    assert success is False
    calls = [str(call) for call in mock_cursor.execute.call_args_list]
    assert any("session_replication_role = 'replica'" in c for c in calls)
    assert any("session_replication_role = 'origin'" in c for c in calls)

