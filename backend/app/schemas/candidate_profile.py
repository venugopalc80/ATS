from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator


class EmploymentBase(BaseModel):
    employer_name: str = Field(min_length=1, max_length=200)
    job_title: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    employment_type: str | None = Field(default=None, max_length=80)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date")
        if self.is_current and self.end_date:
            raise ValueError("Current employment cannot have an end_date")
        return self


class EducationBase(BaseModel):
    institution_name: str = Field(min_length=1, max_length=200)
    qualification: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    grade: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date")
        return self


class CertificationBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuing_organisation: str | None = Field(default=None, max_length=200)
    credential_id: str | None = Field(default=None, max_length=200)
    credential_url: HttpUrl | None = None
    issued_on: date | None = None
    expires_on: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expires_on cannot precede issued_on")
        return self


class LanguageBase(BaseModel):
    language: str = Field(min_length=1, max_length=100)
    proficiency: str | None = None

    @model_validator(mode="after")
    def validate_proficiency(self):
        allowed = {"basic", "conversational", "professional", "fluent", "native"}
        if self.proficiency is not None and self.proficiency not in allowed:
            raise ValueError("Unsupported language proficiency")
        return self


class CandidateProfileRecordOut(BaseModel):
    id: UUID
    organization_id: UUID
    candidate_id: UUID
    created_at: datetime
    updated_at: datetime
