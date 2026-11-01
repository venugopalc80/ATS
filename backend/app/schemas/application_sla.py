from datetime import time, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class ApplicationSLAPolicyUpdate(BaseModel):
    organization_id: UUID
    initial_review_minutes: int = Field(default=1440, ge=1, le=43200)
    first_recruiter_action_minutes: int = Field(default=2880, ge=1, le=43200)
    candidate_follow_up_minutes: int = Field(default=2880, ge=1, le=43200)
    post_interview_update_minutes: int = Field(default=1440, ge=1, le=43200)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    business_days_only: bool = True
    business_hours_start: time = time(9, 0)
    business_hours_end: time = time(17, 0)
    working_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA time zone") from exc
        return normalized

    @field_validator("working_days")
    @classmethod
    def valid_working_days(cls, value: list[int]) -> list[int]:
        if not value or len(value) > 7 or len(set(value)) != len(value):
            raise ValueError("working_days must contain 1 to 7 unique weekdays")
        if any(day < 1 or day > 7 for day in value):
            raise ValueError("working_days values must be ISO weekdays 1 through 7")
        return sorted(value)

    @model_validator(mode="after")
    def valid_business_hours(self):
        if self.business_hours_end <= self.business_hours_start:
            raise ValueError("business_hours_end must be later than business_hours_start")
        return self


class ApplicationSLAPolicyOut(BaseModel):
    organization_id: UUID
    initial_review_minutes: int
    first_recruiter_action_minutes: int
    candidate_follow_up_minutes: int
    post_interview_update_minutes: int
    timezone: str
    business_days_only: bool
    business_hours_start: time
    business_hours_end: time
    working_days: list[int]
    enabled: bool
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class ApplicationSLADeadlineOut(BaseModel):
    id: UUID
    organization_id: UUID
    application_id: UUID
    milestone: str
    starts_at: datetime
    due_at: datetime
    status: str
    completed_at: datetime | None
    last_calculated_at: datetime
    created_at: datetime
    updated_at: datetime
