"""add_cluster_system

Revision ID: a1b2c3d4e5f6
Revises: f1b2c3d4e5f6
Create Date: 2026-10-21 11:44:00.000000

Adds cluster-based access control:
- clusters table (location/site representation)
- user_cluster_memberships table (user <-> cluster with role)
- cluster_role_permissions table (granular permissions per cluster per role)
- cluster_id column on dev_table
- cluster_id column on rooms
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create clusters table
    op.create_table(
        'clusters',
        sa.Column('id', sa.String(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_clusters_name', 'clusters', ['name'], unique=True)
    op.create_index('ix_clusters_is_active', 'clusters', ['is_active'], unique=False)

    # 2. Create user_cluster_memberships table
    op.create_table(
        'user_cluster_memberships',
        sa.Column('id', sa.String(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cluster_id', sa.String(), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('user_id', 'cluster_id', name='uq_user_cluster'),
    )
    op.create_index('ix_user_cluster_memberships_user_id', 'user_cluster_memberships', ['user_id'], unique=False)
    op.create_index('ix_user_cluster_memberships_cluster_id', 'user_cluster_memberships', ['cluster_id'], unique=False)

    # 3. Create cluster_role_permissions table
    op.create_table(
        'cluster_role_permissions',
        sa.Column('id', sa.String(), primary_key=True, nullable=False),
        sa.Column('cluster_id', sa.String(), sa.ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('permission', sa.String(), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.UniqueConstraint('cluster_id', 'role', 'permission', name='uq_cluster_role_permission'),
    )
    op.create_index('ix_cluster_role_permissions_cluster_role', 'cluster_role_permissions', ['cluster_id', 'role'], unique=False)

    # 4. Add cluster_id to dev_table (nullable, safe migration)
    # Use batch mode for SQLite FK constraint compatibility
    with op.batch_alter_table('dev_table') as batch_op:
        batch_op.add_column(sa.Column('cluster_id', sa.String(), nullable=True))
        batch_op.create_index('ix_dev_table_cluster_id', ['cluster_id'], unique=False)

    # 5. Add cluster_id to rooms (nullable, safe migration)
    with op.batch_alter_table('rooms') as batch_op:
        batch_op.add_column(sa.Column('cluster_id', sa.String(), nullable=True))

    # 6. Migrate existing 'admin' users to 'root' role — the first admin becomes root
    # All users keep their existing role column value; root migration is done manually
    # via the create_root_user.py script or by running the server CLI helper.


def downgrade() -> None:
    # Remove cluster_id from rooms
    with op.batch_alter_table('rooms') as batch_op:
        batch_op.drop_column('cluster_id')

    # Remove cluster_id index and column from dev_table
    with op.batch_alter_table('dev_table') as batch_op:
        batch_op.drop_index('ix_dev_table_cluster_id')
        batch_op.drop_column('cluster_id')

    # Drop cluster_role_permissions
    op.drop_index('ix_cluster_role_permissions_cluster_role', table_name='cluster_role_permissions')
    op.drop_table('cluster_role_permissions')

    # Drop user_cluster_memberships
    op.drop_index('ix_user_cluster_memberships_cluster_id', table_name='user_cluster_memberships')
    op.drop_index('ix_user_cluster_memberships_user_id', table_name='user_cluster_memberships')
    op.drop_table('user_cluster_memberships')

    # Drop clusters
    op.drop_index('ix_clusters_is_active', table_name='clusters')
    op.drop_index('ix_clusters_name', table_name='clusters')
    op.drop_table('clusters')
