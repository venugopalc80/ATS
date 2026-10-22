from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

CandidateStatus = Literal["active", "inactive", "placed", "do_not_contact"]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class CandidateBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: CountryCode | None = None
    status: CandidateStatus = "active"
    current_title: str | None = Field(default=None, max_length=200)
    years_experience: Decimal | None = Field(default=None, ge=0, le=80)
    skills: list[str] = Field(default_factory=list)
    ai_summary: str | None = None

    model_config = {"extra": "forbid"}


class CandidateCreate(CandidateBase):
    organization_id: UUID


class CandidateUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: CountryCode | None = None
    status: CandidateStatus | None = None
    current_title: str | None = Field(default=None, max_length=200)
    years_experience: Decimal | None = Field(default=None, ge=0, le=80)
    skills: list[str] | None = None
    ai_summary: str | None = None

    model_config = {"extra": "forbid"}


class CandidateOut(BaseModel):
    id: UUID
    organization_id: UUID
    first_name: str
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    status: CandidateStatus
    current_title: str | None = None
    years_experience: Decimal | None = None
    skills: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
