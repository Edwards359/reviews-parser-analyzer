from datetime import datetime

from app.models.review import ReviewStatus, ReviewTone
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "parent_id": None,
                    "name": "Иван",
                    "text": "Всё супер, быстрая доставка, спасибо!",
                }
            ]
        }
    )

    parent_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Review text cannot be empty.")
        return value


class AIReplyCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "parent_id": 42,
                    "name": "AI Support",
                    "text": "Благодарим за отзыв! Рады, что вам всё понравилось.",
                }
            ]
        }
    )

    parent_id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reply text cannot be empty.")
        return value


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str | None
    text: str
    status: ReviewStatus
    response: str | None
    tone: str | None
    language: str | None = None
    is_ai: bool = False
    retry_count: int = 0
    last_error: str | None = None
    created_at: datetime


class ReviewUpdate(BaseModel):
    status: ReviewStatus | None = None
    response: str | None = None
    tone: ReviewTone | None = None
    last_error: str | None = None


class ReviewListResponse(BaseModel):
    items: list[ReviewRead]
    total: int
    limit: int
    offset: int


class ClaimResponse(BaseModel):
    items: list[ReviewRead]
