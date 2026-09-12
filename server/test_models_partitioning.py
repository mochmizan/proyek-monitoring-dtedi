# test_models_partitioning.py
"""
Unit tests locking invariants for Phase 1:
- Dual-target declarative schema models (data_table, temperature_data, ats_data)
- Composite primary key on (data_id, timestamp) across all 3 telemetry models
- postgresql_partition_by = 'RANGE (timestamp)' in __table_args__
- BRIN indexes declared on timestamp with pages_per_range=32 and autosummarize=True
- Full CRUD lifecycle (insert, update, query, unique constraint) on SQLite 3 WAL
"""

import os
import tempfile
import uuid
from datetime import datetime, UTC, timedelta
import pytest
from sqlalchemy import create_engine, text, inspect, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from databasev5 import Base, set_sqlite_pragma, get_engine_kwargs
import modelsv5
from modelsv5 import (
    hub_table,
    dev_table,
    data_table,
    temperature_data,
    ats_data,
)
import init_sqlv5


@pytest.fixture
def wal_db():
    """Create a temporary SQLite database in WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    tmp_url = f"sqlite:///{tmp_path}"
    kwargs = get_engine_kwargs(tmp_url)
    engine = create_engine(tmp_url, **kwargs)
    event.listen(engine, "connect", set_sqlite_pragma)

    # Initialize schema
    init_sqlv5.init_db(engine)

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()

    yield engine, session

    session.close()
    engine.dispose()
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def test_composite_primary_keys_declared():
    """Verify all 3 telemetry models declare a composite primary key on (data_id, timestamp)."""
    telemetry_models = [data_table, temperature_data, ats_data]

    for model in telemetry_models:
        pk_col_names = [col.name for col in model.__table__.primary_key.columns]
        assert pk_col_names == ["data_id", "timestamp"], (
            f"Model {model.__tablename__} must have composite primary key ['data_id', 'timestamp'], "
            f"got: {pk_col_names}"
        )


def test_postgresql_partition_by_declared():
    """Verify all 3 telemetry models declare postgresql_partition_by RANGE (timestamp)."""
    telemetry_models = [data_table, temperature_data, ats_data]

    for model in telemetry_models:
        # Check __table_args__ contains partition definition
        has_partition_arg = any(
            isinstance(arg, dict) and arg.get("postgresql_partition_by") == "RANGE (timestamp)"
            for arg in model.__table_args__
        )
        assert has_partition_arg, (
            f"Model {model.__tablename__} must declare "
            "{'postgresql_partition_by': 'RANGE (timestamp)'} in __table_args__"
        )
        # Check dialect_options
        assert model.__table__.dialect_options["postgresql"]["partition_by"] == "RANGE (timestamp)"


def test_brin_indexes_declared():
    """Verify BRIN indexes on timestamp are declared with pages_per_range=32 and autosummarize=True."""
    expected_brin = {
        "data_table": "idx_data_table_ts_brin",
        "temperature_data": "idx_temp_ts_brin",
        "ats_data": "idx_ats_ts_brin",
    }

    for model in [data_table, temperature_data, ats_data]:
        tbl_name = model.__tablename__
        expected_idx_name = expected_brin[tbl_name]

        matching_indexes = [
            idx for idx in model.__table__.indexes
            if idx.name == expected_idx_name
        ]
        assert len(matching_indexes) == 1, (
            f"Table {tbl_name} must declare index '{expected_idx_name}'"
        )
        idx = matching_indexes[0]
        col_names = [c.name for c in idx.columns]
        assert col_names == ["timestamp"], (
            f"Index {expected_idx_name} on {tbl_name} must target column 'timestamp', got {col_names}"
        )

        pg_opts = idx.dialect_options.get("postgresql", {})
        assert pg_opts.get("using") == "brin", (
            f"Index {expected_idx_name} on {tbl_name} must use postgresql_using='brin'"
        )
        with_opts = pg_opts.get("with", {})
        assert with_opts.get("pages_per_range") == 32, (
            f"Index {expected_idx_name} on {tbl_name} must specify pages_per_range=32"
        )
        assert with_opts.get("autosummarize") is True, (
            f"Index {expected_idx_name} on {tbl_name} must specify autosummarize=True"
        )


def test_sqlite_wal_clean_crud_and_constraints(wal_db):
    """Verify clean insert, query, update, and unique constraint enforcement on SQLite 3 WAL."""
    engine, db = wal_db

    # Verify journal mode is WAL
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        assert str(journal_mode).lower() == "wal"

    # Seed hub and device
    hub = hub_table(hub_id="HUB_PART_01", hub_name="Part Hub", hub_key="test_key", is_active=True)
    dev = dev_table(dev_id="DEV_PART_01", dev_name="Part Sensor", hub_id="HUB_PART_01", is_active=True)
    db.add_all([hub, dev])
    db.commit()

    base_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)

    # 1. Insert telemetry records
    dt_record = data_table(
        data_id="DT_01",
        timestamp=base_time,
        dev_id="DEV_PART_01",
        dev_name="Part Sensor",
        payload={"v": 1},
    )
    temp_record = temperature_data(
        data_id="TEMP_01",
        timestamp=base_time,
        dev_id="DEV_PART_01",
        temp=26.5,
        humid=60.0,
    )
    ats_record = ats_data(
        data_id="ATS_01",
        timestamp=base_time,
        dev_id="DEV_PART_01",
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
    db.add_all([dt_record, temp_record, ats_record])
    db.commit()

    # 2. Query by composite primary key
    fetched_dt = db.get(data_table, ("DT_01", base_time))
    assert fetched_dt is not None
    assert fetched_dt.payload == {"v": 1}

    fetched_temp = db.get(temperature_data, ("TEMP_01", base_time))
    assert fetched_temp is not None
    assert fetched_temp.temp == 26.5

    fetched_ats = db.get(ats_data, ("ATS_01", base_time))
    assert fetched_ats is not None
    assert fetched_ats.pln == 220.0

    # 3. Update records
    fetched_dt.payload = {"v": 2}
    fetched_temp.temp = 27.0
    fetched_ats.pln = 221.5
    db.commit()

    # Verify updates persisted
    updated_dt = db.get(data_table, ("DT_01", base_time))
    assert updated_dt.payload == {"v": 2}

    updated_temp = db.get(temperature_data, ("TEMP_01", base_time))
    assert updated_temp.temp == 27.0

    updated_ats = db.get(ats_data, ("ATS_01", base_time))
    assert updated_ats.pln == 221.5

    # 4. Range query (leveraging composite B-tree index)
    query_results = (
        db.query(temperature_data)
        .filter(temperature_data.dev_id == "DEV_PART_01")
        .order_by(temperature_data.timestamp.desc())
        .all()
    )
    assert len(query_results) == 1
    assert query_results[0].data_id == "TEMP_01"

    # 5. Unique constraint enforcement (dev_id, timestamp)
    dup_temp = temperature_data(
        data_id="TEMP_02",  # Different data_id
        timestamp=base_time,  # Same dev_id and timestamp
        dev_id="DEV_PART_01",
        temp=30.0,
        humid=50.0,
    )
    db.add(dup_temp)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_sqlite_alembic_upgrade_head_clean(tmp_path):
    """Verify Alembic upgrade head runs cleanly from revision 04a48dbce60b through d2e3f4a5b6c7."""
    import alembic.config
    import alembic.command

    db_file = str(tmp_path / "alembic_test.db")
    db_url = f"sqlite:///{db_file}"

    base_dir = os.path.dirname(os.path.abspath(__file__))
    alembic_ini = os.path.join(base_dir, "alembic.ini")

    cfg = alembic.config.Config(alembic_ini)
    cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Run full upgrade to head
    alembic.command.upgrade(cfg, "head")

    # Verify tables and composite PKs created
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    for tbl in ["data_table", "temperature_data", "ats_data"]:
        assert tbl in tables
        pk = inspector.get_pk_constraint(tbl)
        assert set(pk["constrained_columns"]) == {"data_id", "timestamp"}, (
            f"Table {tbl} PK columns: {pk['constrained_columns']}"
        )

    engine.dispose()
