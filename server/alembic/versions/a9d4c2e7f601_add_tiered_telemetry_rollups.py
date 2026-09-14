"""add tiered telemetry rollups

Revision ID: a9d4c2e7f601
Revises: e7414de216b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9d4c2e7f601"
down_revision: Union[str, Sequence[str], None] = "e7414de216b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("dev_id", sa.String(), sa.ForeignKey("dev_table.dev_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bucket_start", sa.DateTime(timezone=True), primary_key=True),
    ]


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("temperature_hourly", "temperature_daily", "temperature_monthly"):
        if table in existing:
            continue
        columns = _common_columns()
        for metric in ("temp", "humid"):
            columns.extend([
                sa.Column(f"{metric}_sum", sa.Float(), nullable=False, server_default="0"),
                sa.Column(f"{metric}_count", sa.Integer(), nullable=False, server_default="0"),
                sa.Column(f"{metric}_avg", sa.Float(), nullable=True),
                sa.Column(f"{metric}_min", sa.Float(), nullable=True),
                sa.Column(f"{metric}_max", sa.Float(), nullable=True),
            ])
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_dev_bucket", table, ["dev_id", "bucket_start"], unique=True)

    for table in ("ats_hourly", "ats_daily", "ats_monthly"):
        if table in existing:
            continue
        columns = _common_columns()
        for metric in ("pln", "genset", "aki"):
            columns.extend([
                sa.Column(f"{metric}_sum", sa.Float(), nullable=False, server_default="0"),
                sa.Column(f"{metric}_count", sa.Integer(), nullable=False, server_default="0"),
                sa.Column(f"{metric}_avg", sa.Float(), nullable=True),
                sa.Column(f"{metric}_min", sa.Float(), nullable=True),
                sa.Column(f"{metric}_max", sa.Float(), nullable=True),
            ])
        columns.extend([
            sa.Column("first_state", sa.String(), nullable=True),
            sa.Column("last_state", sa.String(), nullable=True),
            sa.Column("first_emergency", sa.Boolean(), nullable=True),
            sa.Column("last_emergency", sa.Boolean(), nullable=True),
            sa.Column("state_change_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("emergency_event_count", sa.Integer(), nullable=False, server_default="0"),
        ])
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_dev_bucket", table, ["dev_id", "bucket_start"], unique=True)


def downgrade() -> None:
    for table in ("ats_monthly", "ats_daily", "ats_hourly", "temperature_monthly", "temperature_daily", "temperature_hourly"):
        op.drop_index(f"ix_{table}_dev_bucket", table_name=table)
        op.drop_table(table)
