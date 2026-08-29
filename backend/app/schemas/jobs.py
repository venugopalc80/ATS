from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

JobStatus = Literal["draft", "open", "on_hold", "closed", "filled", "cancelled"]


class JobCreate(BaseModel):
    organization_id: UUID
    client_id: UUID | None = None
    job_code: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    location: str | None = None
    country_code: Literal["GB", "US", "IN", "AU"] | None = None
    employment_type: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    experience_min: Decimal | None = None
    experience_max: Decimal | None = None
    work_authorization: str | None = None
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    status: JobStatus = "draft"
    recruiter_id: UUID | None = None
    hiring_manager_id: UUID | None = None


class JobOut(JobCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
