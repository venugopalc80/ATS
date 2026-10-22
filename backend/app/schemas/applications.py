from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ApplicationStatus = Literal[
    "new", "screening", "shortlisted", "submitted", "interview", "assessment",
    "offer", "hired", "rejected", "withdrawn"
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


class ApplicationTransition(BaseModel):
    status: ApplicationStatus
    reason: str | None = Field(default=None, max_length=1000)


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


class ApplicationStageHistoryOut(BaseModel):
    id: UUID
    organization_id: UUID
    application_id: UUID
    previous_stage: str | None
    new_stage: str
    actor_user_id: UUID | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStageConfigOut(BaseModel):
    organization_id: UUID
    stage_key: ApplicationStatus
    label: str
    display_order: int
    allowed_next_stages: list[ApplicationStatus]
    is_terminal: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStageConfigUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    display_order: int | None = Field(default=None, ge=0, le=10000)
    allowed_next_stages: list[ApplicationStatus] | None = Field(default=None, max_length=10)
    is_terminal: bool | None = None
    enabled: bool | None = None

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Stage label cannot be blank")
        return value.strip() if value is not None else None

    @field_validator("allowed_next_stages")
    @classmethod
    def unique_next_stages(cls, value: list[ApplicationStatus] | None) -> list[ApplicationStatus] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Allowed next stages must be unique")
        return value
