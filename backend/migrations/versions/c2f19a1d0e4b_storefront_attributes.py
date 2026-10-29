"""add storefront attributes and selected sizes

Revision ID: c2f19a1d0e4b
Revises: b74f6a82dcd9
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f19a1d0e4b"
down_revision: str | Sequence[str] | None = "b74f6a82dcd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("color_name", sa.String(length=100), nullable=True))
    op.add_column(
        "products", sa.Column("sizes", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
    )
    op.add_column("products", sa.Column("compare_at_price", sa.Numeric(12, 2), nullable=True))

    op.add_column(
        "cart_items",
        sa.Column("selected_size", sa.String(length=24), server_default="ONE SIZE", nullable=False),
    )
    op.drop_constraint("uq_cart_items_cart_product", "cart_items", type_="unique")
    op.create_unique_constraint(
        "uq_cart_items_cart_product_size", "cart_items", ["cart_id", "product_id", "selected_size"]
    )

    op.add_column("order_items", sa.Column("selected_size", sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column("order_items", "selected_size")
    op.drop_constraint("uq_cart_items_cart_product_size", "cart_items", type_="unique")
    op.create_unique_constraint(
        "uq_cart_items_cart_product", "cart_items", ["cart_id", "product_id"]
    )
    op.drop_column("cart_items", "selected_size")
    op.drop_column("products", "compare_at_price")
    op.drop_column("products", "sizes")
    op.drop_column("products", "color_name")
    op.drop_column("products", "image_url")
