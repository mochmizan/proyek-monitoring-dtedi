"""schema indexing and nullability

Revision ID: c1a8b9f0e2d3
Revises: b7c9e2f1a4d8
Create Date: 2026-09-02 12:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1a8b9f0e2d3"
down_revision: Union[str, Sequence[str], None] = "b7c9e2f1a4d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_DEFINITIONS = [
    # (table_name, index_name, columns)
    ("event_log", "ix_event_log_dev_metric_ts", ["dev_id", "metric", sa.text("timestamp DESC")]),
    ("event_log", "ix_event_log_room_ts", ["room_id", sa.text("timestamp DESC")]),
    ("event_log", "ix_event_log_dev_resolved", ["dev_id", "resolved_at"]),
    ("event_log", "ix_event_log_ts_desc", [sa.text("timestamp DESC")]),
    ("dev_table", "ix_dev_table_hub_id", ["hub_id"]),
    ("dev_table", "ix_dev_table_room_id", ["room_id"]),
    ("dev_table", "ix_dev_table_dev_name", ["dev_name"]),
    ("pending_commands", "ix_pending_commands_hub_status_created", ["hub_id", "status", "created_at"]),
    ("data_table", "ix_data_table_dev_ts_desc", ["dev_id", sa.text("timestamp DESC")]),
    ("sessions", "ix_sessions_user_expires", ["user_id", "expires_at"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    # 1. Partial Payload Nullability (temperature_data temp & humid nullable=True)
    if "temperature_data" in table_names:
        with op.batch_alter_table("temperature_data") as batch_op:
            batch_op.alter_column("temp", existing_type=sa.Float(), nullable=True)
            batch_op.alter_column("humid", existing_type=sa.Float(), nullable=True)

    # 2. Composite & Lookup Index Creation (idempotent)
    for table_name, index_name, cols in INDEX_DEFINITIONS:
        if table_name in table_names:
            current_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
            if index_name not in current_indexes:
                op.create_index(index_name, table_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    # 1. Drop composite indexes if they exist
    for table_name, index_name, _ in reversed(INDEX_DEFINITIONS):
        if table_name in table_names:
            current_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
            if index_name in current_indexes:
                op.drop_index(index_name, table_name=table_name)

    # 2. Revert nullability of temperature_data temp & humid back to nullable=False
    if "temperature_data" in table_names:
        with op.batch_alter_table("temperature_data") as batch_op:
            batch_op.alter_column("temp", existing_type=sa.Float(), nullable=False)
            batch_op.alter_column("humid", existing_type=sa.Float(), nullable=False)
