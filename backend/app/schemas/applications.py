from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "new", "screening", "submitted", "interview", "offer", "hired", "rejected", "withdrawn"
]


class ApplicationCreate(BaseModel):
    organization_id: UUID
    job_id: UUID
    candidate_id: UUID
    source: str | None = Field(default=None, max_length=100)
    status: ApplicationStatus = "new"


class ApplicationUpdate(BaseModel):
    source: str | None = Field(default=None, max_length=100)
    status: ApplicationStatus | None = None
    match_score: Decimal | None = Field(default=None, ge=0, le=100)
    match_explanation: str | None = None
    human_reviewed: bool | None = None
    human_reviewed_by: UUID | None = None
    human_reviewed_at: datetime | None = None


class ApplicationOut(BaseModel):
    id: UUID
    organization_id: UUID
    job_id: UUID
    candidate_id: UUID
    source: str | None
    status: ApplicationStatus
    match_score: Decimal | None
    match_explanation: str | None
    human_reviewed: bool
    human_reviewed_by: UUID | None
    human_reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
