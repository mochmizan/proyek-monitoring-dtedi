"""add telemetry partitioning and brin

Revision ID: d2e3f4a5b6c7
Revises: c1a8b9f0e2d3
Create Date: 2026-09-12 10:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1a8b9f0e2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # 1. Create Partitioned Parent Tables
        op.execute("""
        CREATE TABLE IF NOT EXISTS data_table (
            data_id VARCHAR NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
            dev_name VARCHAR,
            payload JSONB,
            CONSTRAINT pk_data_table PRIMARY KEY (data_id, timestamp),
            CONSTRAINT uq_data_dev_timestamp UNIQUE (dev_id, timestamp)
        ) PARTITION BY RANGE (timestamp);

        CREATE TABLE IF NOT EXISTS temperature_data (
            data_id VARCHAR NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
            temp FLOAT,
            humid FLOAT,
            CONSTRAINT pk_temperature_data PRIMARY KEY (data_id, timestamp),
            CONSTRAINT uq_temp_dev_timestamp UNIQUE (dev_id, timestamp)
        ) PARTITION BY RANGE (timestamp);

        CREATE TABLE IF NOT EXISTS ats_data (
            data_id VARCHAR NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
            state VARCHAR NOT NULL,
            pln FLOAT NOT NULL,
            genset FLOAT NOT NULL,
            aki FLOAT NOT NULL,
            rem_hour FLOAT NOT NULL,
            rem_min FLOAT NOT NULL,
            rem_sec FLOAT NOT NULL,
            auto_mode BOOLEAN NOT NULL,
            emergency BOOLEAN NOT NULL,
            CONSTRAINT pk_ats_data PRIMARY KEY (data_id, timestamp),
            CONSTRAINT uq_ats_dev_timestamp UNIQUE (dev_id, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """)

        # 2. Attach SARGable B-Tree Indexes & BRIN Indexes to Parent Tables
        op.execute("""
        CREATE INDEX IF NOT EXISTS ix_data_table_dev_ts_desc ON data_table (dev_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_data_table_ts_brin ON data_table USING brin (timestamp) WITH (pages_per_range = 32, autosummarize = true);

        CREATE INDEX IF NOT EXISTS idx_temp_dev_timestamp ON temperature_data (dev_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_temp_ts_brin ON temperature_data USING brin (timestamp) WITH (pages_per_range = 32, autosummarize = true);

        CREATE INDEX IF NOT EXISTS idx_ats_dev_timestamp ON ats_data (dev_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_ats_ts_brin ON ats_data USING brin (timestamp) WITH (pages_per_range = 32, autosummarize = true);
        """)

        # 3. Pre-create Monthly Child Partitions for T-1, T, T+1, T+2
        # CRITICAL: NEVER create a DEFAULT partition (blocks non-blocking concurrent detach)
        op.execute("""
        DO $$
        DECLARE
            tbl TEXT;
            offset_m INT;
            start_ts TIMESTAMPTZ;
            end_ts TIMESTAMPTZ;
            part_suffix TEXT;
        BEGIN
            FOREACH tbl IN ARRAY ARRAY['data_table', 'temperature_data', 'ats_data'] LOOP
                FOR offset_m IN -1..2 LOOP
                    start_ts := date_trunc('month', NOW() + (offset_m || ' month')::INTERVAL);
                    end_ts := date_trunc('month', NOW() + ((offset_m + 1) || ' month')::INTERVAL);
                    part_suffix := to_char(start_ts, 'YYYY_MM');
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS %I_y%s PARTITION OF %I FOR VALUES FROM (%L) TO (%L);',
                        tbl, part_suffix, tbl, start_ts, end_ts
                    );
                END LOOP;
            END LOOP;
        END $$;
        """)

    else:
        # SQLite branch: Standard unpartitioned tables with composite PK (data_id, timestamp)
        inspector = sa.inspect(bind)
        table_names = set(inspector.get_table_names())

        # 1. Ensure tables exist with composite PK
        if "data_table" not in table_names:
            op.create_table(
                "data_table",
                sa.Column("data_id", sa.String(), nullable=False),
                sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
                sa.Column("dev_id", sa.String(), sa.ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=True),
                sa.Column("dev_name", sa.String(), nullable=True),
                sa.Column("payload", sa.JSON().with_variant(sa.String(), "sqlite"), nullable=True),
                sa.PrimaryKeyConstraint("data_id", "timestamp", name="pk_data_table"),
                sa.UniqueConstraint("dev_id", "timestamp", name="uq_data_dev_timestamp"),
            )
        else:
            pk = inspector.get_pk_constraint("data_table")
            if "timestamp" not in pk.get("constrained_columns", []):
                op.execute("""
                    CREATE TABLE data_table__new (
                        data_id VARCHAR NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        dev_id VARCHAR REFERENCES dev_table(dev_id) ON DELETE CASCADE,
                        dev_name VARCHAR,
                        payload TEXT,
                        PRIMARY KEY (data_id, timestamp),
                        CONSTRAINT uq_data_dev_timestamp UNIQUE (dev_id, timestamp)
                    );
                    INSERT INTO data_table__new (data_id, timestamp, dev_id, dev_name, payload)
                        SELECT data_id, timestamp, dev_id, dev_name, payload FROM data_table;
                    DROP TABLE data_table;
                    ALTER TABLE data_table__new RENAME TO data_table;
                """)

        if "temperature_data" not in table_names:
            op.create_table(
                "temperature_data",
                sa.Column("data_id", sa.String(), nullable=False),
                sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
                sa.Column("dev_id", sa.String(), sa.ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False),
                sa.Column("temp", sa.Float(), nullable=True),
                sa.Column("humid", sa.Float(), nullable=True),
                sa.PrimaryKeyConstraint("data_id", "timestamp", name="pk_temperature_data"),
                sa.UniqueConstraint("dev_id", "timestamp", name="uq_temp_dev_timestamp"),
            )
        else:
            pk = inspector.get_pk_constraint("temperature_data")
            if "timestamp" not in pk.get("constrained_columns", []):
                op.execute("""
                    CREATE TABLE temperature_data__new (
                        data_id VARCHAR NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
                        temp FLOAT,
                        humid FLOAT,
                        PRIMARY KEY (data_id, timestamp),
                        CONSTRAINT uq_temp_dev_timestamp UNIQUE (dev_id, timestamp)
                    );
                    INSERT INTO temperature_data__new (data_id, timestamp, dev_id, temp, humid)
                        SELECT data_id, timestamp, dev_id, temp, humid FROM temperature_data;
                    DROP TABLE temperature_data;
                    ALTER TABLE temperature_data__new RENAME TO temperature_data;
                """)

        if "ats_data" not in table_names:
            op.create_table(
                "ats_data",
                sa.Column("data_id", sa.String(), nullable=False),
                sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
                sa.Column("dev_id", sa.String(), sa.ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False),
                sa.Column("state", sa.String(), nullable=False),
                sa.Column("pln", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("genset", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("aki", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("rem_hour", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("rem_min", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("rem_sec", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("auto_mode", sa.Boolean(), nullable=False, server_default="0"),
                sa.Column("emergency", sa.Boolean(), nullable=False, server_default="0"),
                sa.PrimaryKeyConstraint("data_id", "timestamp", name="pk_ats_data"),
                sa.UniqueConstraint("dev_id", "timestamp", name="uq_ats_dev_timestamp"),
            )
        else:
            pk = inspector.get_pk_constraint("ats_data")
            if "timestamp" not in pk.get("constrained_columns", []):
                op.execute("""
                    CREATE TABLE ats_data__new (
                        data_id VARCHAR NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        dev_id VARCHAR NOT NULL REFERENCES dev_table(dev_id) ON DELETE CASCADE,
                        state VARCHAR NOT NULL,
                        pln FLOAT NOT NULL DEFAULT 0.0,
                        genset FLOAT NOT NULL DEFAULT 0.0,
                        aki FLOAT NOT NULL DEFAULT 0.0,
                        rem_hour FLOAT NOT NULL DEFAULT 0.0,
                        rem_min FLOAT NOT NULL DEFAULT 0.0,
                        rem_sec FLOAT NOT NULL DEFAULT 0.0,
                        auto_mode BOOLEAN NOT NULL DEFAULT 0,
                        emergency BOOLEAN NOT NULL DEFAULT 0,
                        PRIMARY KEY (data_id, timestamp),
                        CONSTRAINT uq_ats_dev_timestamp UNIQUE (dev_id, timestamp)
                    );
                    INSERT INTO ats_data__new (data_id, timestamp, dev_id, state, pln, genset, aki, rem_hour, rem_min, rem_sec, auto_mode, emergency)
                        SELECT data_id, timestamp, dev_id, state, pln, genset, aki, rem_hour, rem_min, rem_sec, auto_mode, emergency FROM ats_data;
                    DROP TABLE ats_data;
                    ALTER TABLE ats_data__new RENAME TO ats_data;
                """)

        # 2. Ensure standard indexes exist on SQLite
        inspector = sa.inspect(bind)
        for tbl, idx_name, cols in [
            ("data_table", "ix_data_table_dev_ts_desc", ["dev_id", sa.text("timestamp DESC")]),
            ("data_table", "idx_data_table_ts_brin", ["timestamp"]),
            ("temperature_data", "idx_temp_dev_timestamp", ["dev_id", sa.text("timestamp DESC")]),
            ("temperature_data", "idx_temp_ts_brin", ["timestamp"]),
            ("ats_data", "idx_ats_dev_timestamp", ["dev_id", sa.text("timestamp DESC")]),
            ("ats_data", "idx_ats_ts_brin", ["timestamp"]),
        ]:
            if tbl in inspector.get_table_names():
                current_indexes = {i["name"] for i in inspector.get_indexes(tbl)}
                if idx_name not in current_indexes:
                    op.create_index(idx_name, tbl, cols)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("""
        DROP TABLE IF EXISTS data_table CASCADE;
        DROP TABLE IF EXISTS temperature_data CASCADE;
        DROP TABLE IF EXISTS ats_data CASCADE;
        """)
    else:
        for idx in [
            "idx_ats_ts_brin", "idx_temp_ts_brin", "idx_data_table_ts_brin"
        ]:
            try:
                op.drop_index(idx)
            except Exception:
                pass
