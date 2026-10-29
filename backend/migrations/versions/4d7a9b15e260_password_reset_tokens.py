"""add password reset tokens to users

Revision ID: 4d7a9b15e260
Revises: 3c6f8a12d940
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d7a9b15e260"
down_revision: str | Sequence[str] | None = "3c6f8a12d940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "users", sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_token_hash")
