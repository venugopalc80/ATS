from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

CandidateStatus = Literal["active", "inactive", "placed", "do_not_contact"]
LawfulBasis = Literal["consent", "contract", "legal_obligation", "legitimate_interests", "public_task", "vital_interests"]
CandidateSource = Literal["recruiter_entry", "career_page", "job_application", "referral", "agency", "import", "cv_upload", "other"]
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
    consent_recorded_at: datetime | None = None
    consent_purpose: str | None = Field(default=None, max_length=500)
    retention_until: datetime | None = None
    lawful_basis: LawfulBasis | None = None
    privacy_notice_version: str | None = Field(default=None, max_length=50)
    source_type: CandidateSource = "recruiter_entry"


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
    resume_path: str | None = None
    resume_text: str | None = None
    ai_summary: str | None = None
    consent_recorded_at: datetime | None = None
    consent_purpose: str | None = Field(default=None, max_length=500)
    retention_until: datetime | None = None
    lawful_basis: LawfulBasis | None = None
    privacy_notice_version: str | None = Field(default=None, max_length=50)
    source_type: CandidateSource | None = None


class CandidateOut(CandidateBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
