from datetime import datetime
from enum import StrEnum

from app.db.base import Base
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ReviewStatus(StrEnum):
    NEW = "new"
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    PROCESSED = "processed"
    FAILED = "failed"


class ReviewTone(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id"), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(
            ReviewStatus,
            name="review_status",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=ReviewStatus.NEW,
        nullable=False,
    )
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    parent: Mapped["Review | None"] = relationship(
        "Review",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["Review"]] = relationship(
        "Review",
        back_populates="parent",
        cascade="all, delete-orphan",
    )


Index("ix_reviews_status_created", Review.status, Review.created_at)
