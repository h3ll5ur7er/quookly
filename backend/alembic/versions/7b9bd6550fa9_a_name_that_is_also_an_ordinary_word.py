"""a name that is also an ordinary word

Whether a term may be spotted in a recipe step. Almost always yes; the exception is a
canonical name with another life — German `sieben` is *to sift* and *the number seven*, so
"sieben Minuten backen" would link to a sieve (ADR-055).

Backfilled true, which is what every existing row means: the seed loader is the only thing
that has written here, and it writes the flag itself from now on.

Revision ID: 7b9bd6550fa9
Revises: 5223cf09b215
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7b9bd6550fa9"
down_revision: str | None = "5223cf09b215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("academy_term", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("matchable", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.create_index(batch_op.f("ix_academy_term_matchable"), ["matchable"], unique=False)

    # The default goes once it has done its work: the loader states the flag at the call
    # site, and a column default would quietly answer for a path that forgot to.
    with op.batch_alter_table("academy_term", schema=None) as batch_op:
        batch_op.alter_column("matchable", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("academy_term", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_academy_term_matchable"))
        batch_op.drop_column("matchable")
