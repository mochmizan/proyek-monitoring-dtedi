"""add schedules table

Revision ID: b7c9e2f1a4d8
Revises: 04a48dbce60b
Create Date: 2026-08-29 12:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision: str = 'b7c9e2f1a4d8'
down_revision: Union[str, Sequence[str], None] = '04a48dbce60b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Use Base.metadata.create_all for idempotency if tables exist via init_sqlv5
    # But explicitly create schedules table for alembic history
    from databasev5 import Base
    import modelsv5  # noqa: F401 ensure metadata populated
    # Check if schedules already exists
    inspector = sa.inspect(bind)
    if "schedules" in inspector.get_table_names():
        return
    # Create table
    # Detect dialect for JSON type
    is_pg = bind.dialect.name == "postgresql"
    json_type = JSONB if is_pg else sa.JSON
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dev_id", sa.String(), sa.ForeignKey("dev_table.dev_id", ondelete="CASCADE"), nullable=False),
        sa.Column("hub_id", sa.String(), sa.ForeignKey("hub_table.hub_id", ondelete="CASCADE"), nullable=True),
        sa.Column("cron_expr", sa.String(length=64), nullable=False),
        sa.Column("payload", json_type(), nullable=False),
        sa.Column("tz", sa.String(length=32), nullable=False, server_default="Asia/Jakarta"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1" if not is_pg else "true")),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_schedules_enabled_hub", "schedules", ["enabled", "hub_id"])
    op.create_index("ix_schedules_dev", "schedules", ["dev_id"])


def downgrade() -> None:
    op.drop_index("ix_schedules_dev", table_name="schedules")
    op.drop_index("ix_schedules_enabled_hub", table_name="schedules")
    op.drop_table("schedules")
