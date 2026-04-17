"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-17

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


REVIEW_STATUS_VALUES = ("new", "processing", "awaiting_review", "processed", "failed")


def upgrade() -> None:
    review_status = postgresql.ENUM(
        *REVIEW_STATUS_VALUES, name="review_status", create_type=False
    )
    review_status.create(op.get_bind(), checkfirst=True)
    review_status_col = review_status

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("reviews.id"), nullable=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("is_ai", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "status",
            review_status_col,
            nullable=False,
            server_default="new",
        ),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("tone", sa.String(length=32), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_reviews_status_created", "reviews", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reviews_status_created", table_name="reviews")
    op.drop_table("reviews")
    postgresql.ENUM(name="review_status").drop(op.get_bind(), checkfirst=True)
