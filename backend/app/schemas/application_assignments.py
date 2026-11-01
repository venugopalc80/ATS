from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ApplicationAssignmentUpdate(BaseModel):
    recruiter_id: UUID | None
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Assignment reason cannot be blank")
        return normalized


class ApplicationAssignmentOut(BaseModel):
    application_id: UUID
    organization_id: UUID
    recruiter_id: UUID | None
    assigned_by: UUID | None
    assigned_at: datetime | None
    updated_at: datetime


class ApplicationAssignmentHistoryOut(BaseModel):
    id: UUID
    organization_id: UUID
    application_id: UUID
    previous_recruiter_id: UUID | None
    new_recruiter_id: UUID | None
    actor_user_id: UUID | None
    reason: str
    created_at: datetime
