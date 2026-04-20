from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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


class RemoteReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    parent_id: int | None = None
    name: str | None
    text: str
    status: ReviewStatus
    response: str | None = None
    tone: str | None = None
    language: str | None = None
    is_ai: bool = False
    created_at: datetime


class AIReplyPayload(BaseModel):
    parent_id: int
    name: str | None = None
    text: str


class ReviewUpdatePayload(BaseModel):
    status: ReviewStatus | None = None
    response: str | None = None
    tone: ReviewTone | None = None
    last_error: str | None = None


class AnalysisResult(BaseModel):
    tone: ReviewTone
    reply: str
