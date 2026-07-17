"""Add embedding column to concepts for semantic search.

Revision ID: f3a2b1c0d9e8
Revises: bec77cd80b25
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a2b1c0d9e8"
down_revision: str | Sequence[str] | None = "bec77cd80b25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("concepts") as batch_op:
        batch_op.add_column(sa.Column("embedding", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("concepts") as batch_op:
        batch_op.drop_column("embedding")
