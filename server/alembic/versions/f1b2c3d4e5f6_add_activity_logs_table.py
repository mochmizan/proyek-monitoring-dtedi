"""add_activity_logs_table

Revision ID: f1b2c3d4e5f6
Revises: e7414de216b4
Create Date: 2026-09-16 18:25:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'a9d4c2e7f601'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'activity_logs' not in existing:
        op.create_table(
            'activity_logs',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_name', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('role', sa.String(), nullable=True),
            sa.Column('activity', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_activity_logs_user_name', 'activity_logs', ['user_name'], unique=False)
        op.create_index('ix_activity_logs_created_at', 'activity_logs', ['created_at'], unique=False)
        op.create_index('ix_activity_logs_user_name_created', 'activity_logs', ['user_name', 'created_at'], unique=False)


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'activity_logs' in existing:
        op.drop_index('ix_activity_logs_user_name_created', table_name='activity_logs')
        op.drop_index('ix_activity_logs_created_at', table_name='activity_logs')
        op.drop_index('ix_activity_logs_user_name', table_name='activity_logs')
        op.drop_table('activity_logs')
