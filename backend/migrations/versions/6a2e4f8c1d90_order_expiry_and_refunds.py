"""add order reservation expiry and YooKassa cancellation/refund references

Revision ID: 6a2e4f8c1d90
Revises: 5e8a1c7d3f20
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6a2e4f8c1d90"
down_revision: str | Sequence[str] | None = "5e8a1c7d3f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("payment_cancel_idempotence_key", sa.String(length=36), nullable=True)
    )
    op.add_column("orders", sa.Column("yookassa_refund_id", sa.String(length=64), nullable=True))
    op.add_column(
        "orders", sa.Column("refund_idempotence_key", sa.String(length=36), nullable=True)
    )
    op.add_column("orders", sa.Column("refund_status", sa.String(length=20), nullable=True))
    op.add_column(
        "orders",
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_yookassa_refund_id", "orders", ["yookassa_refund_id"], unique=True)
    op.create_index("ix_orders_reservation_expires_at", "orders", ["reservation_expires_at"])
    op.create_check_constraint(
        "ck_orders_refund_status",
        "orders",
        "refund_status IS NULL OR refund_status IN ('pending', 'succeeded', 'canceled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_refund_status", "orders", type_="check")
    op.drop_index("ix_orders_reservation_expires_at", table_name="orders")
    op.drop_index("ix_orders_yookassa_refund_id", table_name="orders")
    op.drop_column("orders", "reservation_expires_at")
    op.drop_column("orders", "refund_status")
    op.drop_column("orders", "refund_idempotence_key")
    op.drop_column("orders", "yookassa_refund_id")
    op.drop_column("orders", "payment_cancel_idempotence_key")
