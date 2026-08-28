"""Where a food sits.

A category tree, and a nullable pointer from each registry entry into it. The Swiss table
this registry was built from already carries this — every row names a category
hierarchically, in all three published languages — and Quookly was throwing it away.

Nullable, and null for every entry that exists today. Seeding fills it on the next
start-up for the rows that came from the published table; a cook's own entries stay
uncategorised until somebody says otherwise, because a bucket called "other" is a claim
about the food and "nobody has said" is not one.

Two tables rather than two columns, because the tree has to be extendable by hand: a
household that stocks something the Swiss never listed adds a category, not a migration
([ADR-067](../../../doc/07-decisions.md)).

Revision ID: a4a3655b36e9
Revises: 33bef161ea4c
Create Date: 2026-08-28 16:23:01.145345
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

revision: str = "a4a3655b36e9"
down_revision: str | None = "33bef161ea4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredient_category",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["ingredient_category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ingredient_category", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingredient_category_parent_id"), ["parent_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ingredient_category_slug"), ["slug"], unique=True)

    op.create_table(
        "ingredient_category_name",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("locale", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["ingredient_category.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "locale", name="uq_category_name"),
    )
    with op.batch_alter_table("ingredient_category_name", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingredient_category_name_category_id"), ["category_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ingredient_category_name_locale"), ["locale"], unique=False
        )

    with op.batch_alter_table("ingredient", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_ingredient_category_id"), ["category_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_ingredient_category", "ingredient_category", ["category_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("ingredient", schema=None) as batch_op:
        batch_op.drop_constraint("fk_ingredient_category", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_ingredient_category_id"))
        batch_op.drop_column("category_id")

    with op.batch_alter_table("ingredient_category_name", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredient_category_name_locale"))
        batch_op.drop_index(batch_op.f("ix_ingredient_category_name_category_id"))
    op.drop_table("ingredient_category_name")

    with op.batch_alter_table("ingredient_category", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredient_category_slug"))
        batch_op.drop_index(batch_op.f("ix_ingredient_category_parent_id"))
    op.drop_table("ingredient_category")
