"""a recipe can be put away

Archived rather than deleted, because plans, cooked meals and shopping ticks point at a
recipe and a cooked meal that lost its recipe is a hole in a history nobody can fill back
in (ADR-059).

Nullable, so no backfill: every recipe that exists is one nobody has put away, which is
what absent already means here.

Revision ID: ea6b9b7fea01
Revises: 47fd1573810a
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ea6b9b7fea01"
down_revision: str | None = "47fd1573810a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_recipe_archived_at"), ["archived_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_archived_at"))
        batch_op.drop_column("archived_at")
