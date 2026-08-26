"""registry entries are reviewed

Whether anybody has looked at an *entry*, which is not whether anybody classified what is
inside the ingredient (ADR-051). The two are separate columns because more than half the
shipped registry is unclassified — the published table simply could not answer for those
rows — and folding review into that flag would bury the handful an import invented under
four hundred entries that need no review at all.

Backfilled from provenance, which is the only evidence a migration has: a seeded row came
from a table this instance chose to ship and counts as reviewed; anything else was
invented on a cook's behalf by an import and has not been. That errs towards asking for a
second look rather than towards granting one nobody gave.

Revision ID: 47fd1573810a
Revises: 5925124b9ca7
Create Date: 2026-08-26 08:16:52.888490
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "47fd1573810a"
down_revision: str | None = "5925124b9ca7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A server default so the column can be NOT NULL on a table that already has rows.
    # `false` rather than `true`: if the backfill below were somehow not to run, the
    # failure is a queue full of entries that did not need reviewing — tedious, and
    # visibly wrong. The other way round is an entry silently marked as looked at.
    with op.batch_alter_table("ingredient", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index(batch_op.f("ix_ingredient_approved"), ["approved"], unique=False)

    # Stored by enum *name*, which is what SQLAlchemy writes for a Python enum column.
    op.execute("UPDATE ingredient SET approved = 1 WHERE origin = 'SEED'")

    # The default goes once it has done its work. `IngredientAccess.register` states
    # approval at the call site, and a column default would quietly answer for a code path
    # that forgot to.
    with op.batch_alter_table("ingredient", schema=None) as batch_op:
        batch_op.alter_column("approved", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("ingredient", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredient_approved"))
        batch_op.drop_column("approved")
