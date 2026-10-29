"""add size inventory and product image galleries

Revision ID: 91d8a4c73e21
Revises: c2f19a1d0e4b
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "91d8a4c73e21"
down_revision: str | Sequence[str] | None = "c2f19a1d0e4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("stock_by_size", sa.JSON(), nullable=True))
    op.add_column(
        "products",
        sa.Column("image_urls", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    products = sa.table(
        "products",
        sa.column("id", sa.Integer()),
        sa.column("sizes", sa.JSON()),
        sa.column("stock_quantity", sa.Integer()),
        sa.column("image_url", sa.Text()),
        sa.column("stock_by_size", sa.JSON()),
        sa.column("image_urls", sa.JSON()),
    )
    connection = op.get_bind()
    for product in connection.execute(
        sa.select(
            products.c.id,
            products.c.sizes,
            products.c.stock_quantity,
            products.c.image_url,
        )
    ):
        sizes = list(dict.fromkeys(product.sizes or ["ONE SIZE"]))
        quotient, remainder = divmod(product.stock_quantity, len(sizes))
        stock_by_size = {
            size: quotient + (1 if index < remainder else 0) for index, size in enumerate(sizes)
        }
        connection.execute(
            products.update()
            .where(products.c.id == product.id)
            .values(
                stock_by_size=stock_by_size,
                image_urls=[product.image_url] if product.image_url else [],
            )
        )


def downgrade() -> None:
    op.drop_column("products", "image_urls")
    op.drop_column("products", "stock_by_size")
