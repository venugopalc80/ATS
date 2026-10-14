from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

InterviewStatus = Literal["scheduled", "completed", "cancelled", "rescheduled", "no_show"]


def require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Interview date/time must include a timezone offset")
    return value


class InterviewCreate(BaseModel):
    organization_id: UUID
    application_id: UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    interview_type: str = Field(default="video", min_length=2, max_length=50)
    location: str | None = Field(default=None, max_length=500)
    interviewer_ids: list[UUID] = Field(default_factory=list)
    # New interviews always start scheduled; lifecycle changes use the update endpoint.
    status: Literal["scheduled"] = "scheduled"
    notes: str | None = None

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_include_timezone(cls, value: datetime) -> datetime:
        return require_timezone(value)


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    interview_type: str | None = Field(default=None, min_length=2, max_length=50)
    location: str | None = Field(default=None, max_length=500)
    interviewer_ids: list[UUID] | None = None
    status: InterviewStatus | None = None
    notes: str | None = None
    feedback: str | None = None
    outcome: str | None = Field(default=None, max_length=100)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        return require_timezone(value)


class InterviewOut(InterviewCreate):
    id: UUID
    feedback: str | None
    outcome: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
