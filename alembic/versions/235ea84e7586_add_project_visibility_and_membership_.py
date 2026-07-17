"""add_project_visibility_and_membership_tables

Revision ID: 235ea84e7586
Revises: 7927f8912988
Create Date: 2026-07-17 16:25:00.060613

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '235ea84e7586'
down_revision: str | Sequence[str] | None = '7927f8912988'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'workspace_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'project_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # Use batch mode for SQLite compatibility (no native ALTER TABLE ADD CONSTRAINT)
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('visibility', sa.String(length=50), nullable=False, server_default='workspace'))

    with op.batch_alter_table('concepts') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('visibility', sa.String(length=50), nullable=False, server_default='workspace'))
        batch_op.create_foreign_key('fk_concepts_project_id', 'projects', ['project_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('concepts') as batch_op:
        batch_op.drop_constraint('fk_concepts_project_id', type_='foreignkey')
        batch_op.drop_column('visibility')
        batch_op.drop_column('project_id')

    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('visibility')

    op.drop_table('project_members')
    op.drop_table('workspace_members')
