"""add YooKassa payment references to orders

Revision ID: 5e8a1c7d3f20
Revises: 4d7a9b15e260
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e8a1c7d3f20"
down_revision: str | Sequence[str] | None = "4d7a9b15e260"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("yookassa_payment_id", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("payment_confirmation_url", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("payment_idempotence_key", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_orders_yookassa_payment_id",
        "orders",
        ["yookassa_payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_yookassa_payment_id", table_name="orders")
    op.drop_column("orders", "payment_idempotence_key")
    op.drop_column("orders", "payment_confirmation_url")
    op.drop_column("orders", "yookassa_payment_id")
