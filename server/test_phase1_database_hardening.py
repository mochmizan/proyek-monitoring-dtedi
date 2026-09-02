# test_phase1_database_hardening.py
"""
Unit tests for Phase 1: Database Engine Hardening & Session Safety
Covers:
1. SQLite PRAGMAs (WAL, busy_timeout=10000, synchronous=NORMAL, foreign_keys=ON, temp_store=MEMORY)
2. SQLite connect_args driver configuration (timeout=10.0, check_same_thread=False)
3. SQLite foreign key enforcement (IntegrityError on orphan FK insert)
4. PostgreSQL engine kwargs helper (connection pool bounds, recycle, statement timeout, and env overrides)
5. get_db() session success lifecycle (clean session yield and guaranteed close)
6. get_db() session exception lifecycle (automatic rollback and guaranteed close on exception)
7. verify_hub_identity success and presence heartbeat update
8. verify_hub_identity 401 unauthorized handling (missing hub, inactive hub, mismatched key)
9. verify_hub_identity commit failure transaction rollback and HTTP 500 error mapping
"""

import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import verify_hub_identity
from databasev5 import (
    DATABASE_URL,
    Base,
    SessionLocal,
    engine,
    get_db,
    get_engine_kwargs,
    set_sqlite_pragma,
)
from modelsv5 import dev_table, hub_table, rooms, temperature_data, ats_data, pending_commands


def test_sqlite_pragmas_applied():
    """Verify SQLite PRAGMAs are executed on connection checkout."""
    # Test on a temporary file-backed SQLite database with set_sqlite_pragma attached
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tmp_url = f"sqlite:///{tmp_path}"
        tmp_kwargs = get_engine_kwargs(tmp_url)
        test_engine = create_engine(tmp_url, **tmp_kwargs)
        event.listen(test_engine, "connect", set_sqlite_pragma)

        with test_engine.connect() as conn:
            journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
            busy_timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            synchronous = conn.execute(text("PRAGMA synchronous;")).scalar()
            foreign_keys = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            temp_store = conn.execute(text("PRAGMA temp_store;")).scalar()

        # File-based SQLite in WAL mode returns 'wal'
        assert str(journal_mode).lower() == "wal"
        # busy_timeout must be 10000 ms (10 seconds, capped per review feedback)
        assert busy_timeout == 10000
        # synchronous NORMAL is numeric 1
        assert synchronous == 1
        # foreign_keys ON is numeric 1
        assert foreign_keys == 1
        # temp_store MEMORY is numeric 2
        assert temp_store == 2

        test_engine.dispose()

        # Also verify databasev5.engine itself executes these pragmas
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA busy_timeout;")).scalar() == 10000
            assert conn.execute(text("PRAGMA synchronous;")).scalar() == 1
            assert conn.execute(text("PRAGMA foreign_keys;")).scalar() == 1
            assert conn.execute(text("PRAGMA temp_store;")).scalar() == 2
            assert str(conn.execute(text("PRAGMA journal_mode;")).scalar()).lower() in ("wal", "memory")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def test_sqlite_timeout_and_driver_args():
    """Verify SQLite driver arguments set timeout=10.0 and check_same_thread=False."""
    kwargs = get_engine_kwargs("sqlite:///./hubgatev5.db")
    assert "connect_args" in kwargs
    assert kwargs["connect_args"].get("check_same_thread") is False
    assert kwargs["connect_args"].get("timeout") == 10.0
    assert kwargs.get("pool_pre_ping") is True

    # Ensure dialect safety: pool_size/max_overflow/pool_recycle not in SQLite kwargs
    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs
    assert "pool_recycle" not in kwargs


def test_sqlite_foreign_key_enforcement():
    """Verify foreign key constraint violations raise IntegrityError under PRAGMA foreign_keys=ON."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tmp_url = f"sqlite:///{tmp_path}"
        tmp_kwargs = get_engine_kwargs(tmp_url)
        fk_engine = create_engine(tmp_url, **tmp_kwargs)
        event.listen(fk_engine, "connect", set_sqlite_pragma)

        with fk_engine.begin() as conn:
            conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY);"))
            conn.execute(
                text(
                    "CREATE TABLE child ("
                    "  id INTEGER PRIMARY KEY,"
                    "  parent_id INTEGER NOT NULL REFERENCES parent(id)"
                    ");"
                )
            )

        # Inserting a child with non-existent parent_id must violate foreign key constraint
        with pytest.raises(IntegrityError):
            with fk_engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO child (parent_id) VALUES (9999);")
                )

        fk_engine.dispose()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def test_postgres_engine_kwargs_configuration():
    """Verify PostgreSQL engine arguments: pool bounds, recycle, pre_ping, and statement_timeout."""
    pg_url = "postgresql://user:password@localhost:5432/smsb"

    # 1. Defaults verification
    defaults = get_engine_kwargs(pg_url)
    assert defaults["pool_size"] == 10
    assert defaults["max_overflow"] == 5
    assert defaults["pool_recycle"] == 1800
    assert defaults["pool_pre_ping"] is True
    assert defaults["connect_args"]["options"] == "-c statement_timeout=15000"
    assert defaults["echo"] is False

    # 2. Environment overrides verification
    with patch.dict(
        os.environ,
        {
            "DB_POOL_SIZE": "25",
            "DB_MAX_OVERFLOW": "10",
            "DB_POOL_RECYCLE": "3600",
            "DB_STATEMENT_TIMEOUT_MS": "25000",
            "DB_ECHO": "true",
        },
    ):
        overrides = get_engine_kwargs(pg_url)
        assert overrides["pool_size"] == 25
        assert overrides["max_overflow"] == 10
        assert overrides["pool_recycle"] == 3600
        assert overrides["pool_pre_ping"] is True
        assert overrides["connect_args"]["options"] == "-c statement_timeout=25000"
        assert overrides["echo"] is True


def test_get_db_session_success_lifecycle():
    """Verify get_db() yields an active Session and closes cleanly on completion."""
    gen = get_db()
    db = next(gen)

    assert isinstance(db, Session)
    assert db.is_active

    # Closing generator simulates route completion
    with pytest.raises(StopIteration):
        next(gen)

    # With mock session, verify close() is called and rollback() is not called
    mock_session = MagicMock()
    with patch("databasev5.SessionLocal", return_value=mock_session):
        gen2 = get_db()
        sess = next(gen2)
        assert sess == mock_session
        with pytest.raises(StopIteration):
            next(gen2)

        mock_session.close.assert_called_once()
        mock_session.rollback.assert_not_called()


def test_get_db_session_exception_rollback():
    """Verify get_db() triggers rollback() and close() when an unhandled exception occurs."""
    mock_session = MagicMock()
    with patch("databasev5.SessionLocal", return_value=mock_session):
        gen = get_db()
        sess = next(gen)
        assert sess == mock_session

        # Throw exception inside the generator (simulating endpoint failure)
        with pytest.raises(RuntimeError, match="Unhandled route error"):
            gen.throw(RuntimeError("Unhandled route error"))

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


def test_verify_hub_identity_success_and_presence():
    """Verify verify_hub_identity validates credentials, stages presence heartbeat, and DOES NOT commit (CRIT-01)."""
    from app.dependencies import hub_auth_cache
    hub_auth_cache.clear()

    mock_hub = MagicMock(spec=hub_table)
    mock_hub.hub_id = "HUB-VAL-01"
    mock_hub.hub_name = "Test Hub 1"
    mock_hub.hub_key = "secret_key_12345"
    mock_hub.is_active = True
    mock_hub.last_seen = None

    mock_db = MagicMock(spec=Session)
    mock_db.get.return_value = mock_hub

    start_time = datetime.now(UTC)
    result = verify_hub_identity(
        x_hub_id="HUB-VAL-01",
        x_hub_key="secret_key_12345",
        db=mock_db,
    )
    end_time = datetime.now(UTC)

    assert result == mock_hub
    assert mock_hub.last_seen is not None
    assert start_time <= mock_hub.last_seen <= end_time
    # Phase 4 (CRIT-01): ZERO commit inside dependency to eliminate double-commit lock contention
    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_not_called()


def test_verify_hub_identity_unauthorized_does_not_leak():
    """Verify verify_hub_identity raises 401 on non-existent, inactive, or bad-key hub."""
    from app.dependencies import hub_auth_cache
    hub_auth_cache.clear()

    mock_db = MagicMock(spec=Session)

    # 1. Hub not found
    mock_db.get.return_value = None
    with pytest.raises(HTTPException) as exc_info_not_found:
        verify_hub_identity(
            x_hub_id="UNKNOWN_HUB",
            x_hub_key="any_key",
            db=mock_db,
        )
    assert exc_info_not_found.value.status_code == 401
    mock_db.commit.assert_not_called()

    # 2. Hub inactive
    hub_auth_cache.clear()
    inactive_hub = MagicMock(spec=hub_table)
    inactive_hub.hub_name = "Inactive Hub"
    inactive_hub.is_active = False
    inactive_hub.hub_key = "key123"
    mock_db.get.return_value = inactive_hub
    with pytest.raises(HTTPException) as exc_info_inactive:
        verify_hub_identity(
            x_hub_id="INACTIVE_HUB",
            x_hub_key="key123",
            db=mock_db,
        )
    assert exc_info_inactive.value.status_code == 401
    mock_db.commit.assert_not_called()

    # 3. Hub key mismatch
    hub_auth_cache.clear()
    active_hub = MagicMock(spec=hub_table)
    active_hub.hub_name = "Active Hub"
    active_hub.is_active = True
    active_hub.hub_key = "correct_secret"
    mock_db.get.return_value = active_hub
    with pytest.raises(HTTPException) as exc_info_bad_key:
        verify_hub_identity(
            x_hub_id="ACTIVE_HUB",
            x_hub_key="wrong_secret",
            db=mock_db,
        )
    assert exc_info_bad_key.value.status_code == 401
    mock_db.commit.assert_not_called()


def test_verify_hub_identity_zero_commit_guarantee():
    """Verify verify_hub_identity executes zero db.commit() calls to avoid premature transaction commit."""
    from app.dependencies import hub_auth_cache
    hub_auth_cache.clear()

    valid_hub = MagicMock(spec=hub_table)
    valid_hub.hub_id = "HUB-ZERO-01"
    valid_hub.hub_name = "Zero Commit Hub"
    valid_hub.hub_key = "valid_key_999"
    valid_hub.is_active = True
    valid_hub.last_seen = None

    mock_db = MagicMock(spec=Session)
    mock_db.get.return_value = valid_hub

    result = verify_hub_identity(
        x_hub_id="HUB-ZERO-01",
        x_hub_key="valid_key_999",
        db=mock_db,
    )
    assert result == valid_hub
    mock_db.commit.assert_not_called()


def test_models_relationship_batch_insert_order():
    """Verify that SQLAlchemy UnitOfWork flushes parent-first when models are added in reverse order."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tmp_url = f"sqlite:///{tmp_path}"
        tmp_kwargs = get_engine_kwargs(tmp_url)
        test_engine = create_engine(tmp_url, **tmp_kwargs)
        event.listen(test_engine, "connect", set_sqlite_pragma)

        Base.metadata.create_all(bind=test_engine)
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
        db = TestSession()

        try:
            # Create parent and child objects
            hub = hub_table(
                hub_id="HUB_REL_01",
                hub_name="Rel Hub",
                hub_key="secret_rel",
                is_active=True,
            )
            room = rooms(
                id="ROOM_REL_01",
                name="Rel Room",
                hub_id="HUB_REL_01",
            )
            dev = dev_table(
                dev_id="DEV_REL_01",
                dev_name="Rel Device",
                dev_type="TS",
                hub_id="HUB_REL_01",
                room_id="ROOM_REL_01",
                is_active=True,
            )
            temp = temperature_data(
                data_id="TEMP_REL_01",
                dev_id="DEV_REL_01",
                timestamp=datetime.now(UTC),
                temp=24.5,
                humid=55.0,
            )
            ats = ats_data(
                data_id="ATS_REL_01",
                dev_id="DEV_REL_01",
                timestamp=datetime.now(UTC),
                state="PLN_ON",
                pln=220.0,
                genset=0.0,
                aki=12.5,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False,
            )

            # Add in reverse child-first order to session
            db.add_all([ats, temp, dev, room, hub])

            # Commit must succeed without foreign key violations due to modelsv5 relationship metadata
            db.commit()

            # Verify rows exist and relationships can be navigated
            fetched_dev = db.get(dev_table, "DEV_REL_01")
            assert fetched_dev is not None
            assert fetched_dev.hub.hub_id == "HUB_REL_01"
            assert len(fetched_dev.temperature_records) == 1
            assert len(fetched_dev.ats_records) == 1
            assert fetched_dev.ats_records[0].data_id == "ATS_REL_01"

        finally:
            db.close()
            test_engine.dispose()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def test_models_relationship_cascade_deletion():
    """Verify that deleting a parent dev_table cascades deletion to child telemetry records."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tmp_url = f"sqlite:///{tmp_path}"
        tmp_kwargs = get_engine_kwargs(tmp_url)
        test_engine = create_engine(tmp_url, **tmp_kwargs)
        event.listen(test_engine, "connect", set_sqlite_pragma)

        Base.metadata.create_all(bind=test_engine)
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
        db = TestSession()

        try:
            hub = hub_table(hub_id="HUB_CAS_01", hub_name="Cas Hub", hub_key="k", is_active=True)
            dev = dev_table(dev_id="DEV_CAS_01", dev_name="Cas Dev", hub_id="HUB_CAS_01", is_active=True)
            temp = temperature_data(data_id="TEMP_CAS_01", dev_id="DEV_CAS_01", timestamp=datetime.now(UTC), temp=20.0, humid=50.0)
            ats = ats_data(
                data_id="ATS_CAS_01",
                dev_id="DEV_CAS_01",
                timestamp=datetime.now(UTC),
                state="PLN_ON",
                pln=220.0,
                genset=0.0,
                aki=12.0,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False,
            )
            db.add_all([hub, dev, temp, ats])
            db.commit()

            # Delete dev_table parent
            db.delete(dev)
            db.commit()

            # Verify child telemetry records were cascaded
            assert db.get(temperature_data, "TEMP_CAS_01") is None
            assert db.get(ats_data, "ATS_CAS_01") is None

        finally:
            db.close()
            test_engine.dispose()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def test_orphan_child_row_raises_integrity_error():
    """Verify that inserting an orphan child row violates foreign key constraint and raises IntegrityError."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tmp_url = f"sqlite:///{tmp_path}"
        tmp_kwargs = get_engine_kwargs(tmp_url)
        test_engine = create_engine(tmp_url, **tmp_kwargs)
        event.listen(test_engine, "connect", set_sqlite_pragma)

        Base.metadata.create_all(bind=test_engine)
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
        db = TestSession()

        try:
            # Inserting ats_data pointing to non-existent dev_id must fail under PRAGMA foreign_keys=ON
            orphan_ats = ats_data(
                data_id="ATS_ORPHAN_01",
                dev_id="NON_EXISTENT_DEV_ID",
                timestamp=datetime.now(UTC),
                state="PLN_ON",
                pln=220.0,
                genset=0.0,
                aki=12.0,
                rem_hour=0.0,
                rem_min=0.0,
                rem_sec=0.0,
                auto_mode=True,
                emergency=False,
            )
            db.add(orphan_ats)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        finally:
            db.close()
            test_engine.dispose()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
