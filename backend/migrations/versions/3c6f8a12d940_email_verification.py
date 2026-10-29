"""add email verification to users

Revision ID: 3c6f8a12d940
Revises: 7b41c9d28a60
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c6f8a12d940"
down_revision: str | Sequence[str] | None = "7b41c9d28a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "users", sa.Column("verification_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "users", sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "verification_expires_at")
    op.drop_column("users", "verification_token_hash")
    op.drop_column("users", "email_verified")
