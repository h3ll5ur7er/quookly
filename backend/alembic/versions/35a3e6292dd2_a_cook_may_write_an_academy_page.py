"""a cook may write an academy page

Two columns, both nullable so neither needs a backfill.

`written_by` is absent for every page that exists, which is the truth: they were all
seeded, and nobody on this instance wrote them. It is what lets an author rewrite their
own page while nobody has approved it (ADR-060).

`archived_at` is how an administrator declines one — put away rather than destroyed, the
same choice a recipe makes for the same reason.

Revision ID: 35a3e6292dd2
Revises: 1a99ba24932b
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "35a3e6292dd2"
down_revision: str | None = "1a99ba24932b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("academy_page", schema=None) as batch_op:
        batch_op.add_column(sa.Column("written_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_academy_page_written_by"), ["written_by"])
        batch_op.create_index(batch_op.f("ix_academy_page_archived_at"), ["archived_at"])
        batch_op.create_foreign_key(
            "fk_academy_page_written_by_cook", "cook", ["written_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("academy_page", schema=None) as batch_op:
        batch_op.drop_constraint("fk_academy_page_written_by_cook", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_academy_page_archived_at"))
        batch_op.drop_index(batch_op.f("ix_academy_page_written_by"))
        batch_op.drop_column("archived_at")
        batch_op.drop_column("written_by")
