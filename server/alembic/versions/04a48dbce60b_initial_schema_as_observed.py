"""initial schema as observed

Revision ID: 04a48dbce60b
Revises: 
Create Date: 2026-08-27 18:06:43.292552
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04a48dbce60b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Full schema as observed from modelsv5.py — idempotent create via Base.metadata
    # This migration represents the current schema; existing DBs already have these tables
    # via init_sqlv5.py's Base.metadata.create_all + additive migrations. Alembic upgrade
    # will be a no-op if tables already exist, otherwise creates them.
    from databasev5 import Base
    import modelsv5  # noqa: F401 ensure all models imported
    bind = op.get_bind()
    # create_all is idempotent — will skip existing tables
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Drop all tables in reverse dependency order
    from databasev5 import Base
    import modelsv5  # noqa: F401
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
