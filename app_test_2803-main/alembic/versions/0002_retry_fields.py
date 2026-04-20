"""retry_count and last_error columns

Revision ID: 0002_retry_fields
Revises: 0001_initial
Create Date: 2026-04-20

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_retry_fields"
down_revision: str | None = "0001_initial"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reviews",
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reviews", "last_error")
    op.drop_column("reviews", "retry_count")
