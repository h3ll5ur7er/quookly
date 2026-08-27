"""a recipe records the language it is written in

Nullable, and deliberately not backfilled. Every recipe stored before this was stored
without anybody recording what it was written in, and setting them all to English would
be inventing the one fact this column exists to stop inventing (ADR-032).

A bare language code — `de`, not `de-CH`. The region is a punctuation habit; what matters
is what a translation would be translating out of.

Revision ID: 4705ba7d6af6
Revises: 7cd9f5cb86c6
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4705ba7d6af6"
down_revision: str | None = "7cd9f5cb86c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.add_column(sa.Column("language", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipe", schema=None) as batch_op:
        batch_op.drop_column("language")
