"""How much of the recipe a meal makes.

A yield the cook set by hand, in the recipe's own unit: 8 of a recipe that makes 4 is
twice it. Nullable, and null for every slot that exists today — absent means the two rules
that applied before anybody could say otherwise, one batch or as many as the table wants.

It lives on the slot rather than on the cooking session because the shopping list and the
stock reservation are the slot's, and a session making three batches of a meal that
reserved one is the disagreement `Sizing` exists to prevent (D6).

Revision ID: 33bef161ea4c
Revises: 22bbd9f87fba
Create Date: 2026-08-28 13:48:25.416608
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "33bef161ea4c"
down_revision: str | None = "22bbd9f87fba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plan_slot", schema=None) as batch_op:
        batch_op.add_column(sa.Column("servings", sa.Numeric(precision=12, scale=4), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plan_slot", schema=None) as batch_op:
        batch_op.drop_column("servings")
