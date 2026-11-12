from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

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
    resume_path: str | None = None
    resume_text: str | None = None
    ai_summary: str | None = None


class CandidateCreate(CandidateBase):
    organization_id: UUID
    # Consent and retention metadata are system-managed, never client-authored.
    model_config = ConfigDict(extra="forbid")


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
    resume_path: str | None = None
    resume_text: str | None = None
    ai_summary: str | None = None
    # Prevent silently accepting fields outside the candidate update contract.
    model_config = ConfigDict(extra="forbid")


class CandidateOut(CandidateBase):
    consent_recorded_at: datetime | None = None
    consent_purpose: str | None = None
    retention_until: datetime | None = None
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
