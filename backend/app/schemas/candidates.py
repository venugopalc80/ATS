from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

CandidateStatus = Literal["active", "inactive", "placed", "do_not_contact"]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class CandidateBase(BaseModel):
    @field_validator("profile_links")
    @classmethod
    def validate_profile_links(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        if len(value) > 20:
            raise ValueError("At most 20 profile links are allowed")
        cleaned = []
        for item in value:
            kind, url = item.get("type", ""), item.get("url", "")
            parsed = urlparse(url)
            if kind not in {"linkedin", "github", "portfolio"} or parsed.scheme not in {"http", "https"} or not parsed.netloc or len(url) > 2048:
                raise ValueError("Profile links must have a supported type and a valid HTTP(S) URL")
            cleaned.append({"type": kind, "url": url})
        return cleaned

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
    profile_links: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    resume_path: str | None = None
    resume_text: str | None = None
    ai_summary: str | None = None
    consent_recorded_at: datetime | None = None
    consent_purpose: str | None = None
    retention_until: datetime | None = None


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
    skills: list[str] | None = Field(default=None, max_length=100)
    profile_links: list[dict[str, str]] | None = Field(default=None, max_length=20)
    resume_path: str | None = None
    resume_text: str | None = None
    ai_summary: str | None = None
    consent_recorded_at: datetime | None = None
    consent_purpose: str | None = None
    retention_until: datetime | None = None


class CandidateOut(CandidateBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
