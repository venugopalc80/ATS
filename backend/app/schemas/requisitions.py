from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

RequisitionStatus = Literal["draft","pending_approval","approved","rejected","converted","cancelled"]

class RequisitionFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=160)
    client_id: UUID | None = None
    hiring_manager_id: UUID | None = None
    recruiter_id: UUID | None = None
    headcount: int = Field(default=1, ge=1, le=10000)
    justification: str = Field(min_length=1, max_length=10000)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=240)
    country_code: Literal["GB","US","IN","AU"] | None = None
    employment_type: str | None = Field(default=None, max_length=80)
    work_mode: str | None = Field(default=None, max_length=40)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    target_start_date: date | None = None
    target_close_date: date | None = None

    @field_validator("title","justification")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("salary_currency")
    @classmethod
    def normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_max < self.budget_min:
            raise ValueError("budget_max must be greater than or equal to budget_min")
        if self.salary_min is not None and self.salary_max is not None and self.salary_max < self.salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        if self.target_start_date and self.target_close_date and self.target_close_date < self.target_start_date:
            raise ValueError("target_close_date cannot be earlier than target_start_date")
        return self

class RequisitionCreate(RequisitionFields):
    organization_id: UUID

class RequisitionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=160)
    client_id: UUID | None = None
    hiring_manager_id: UUID | None = None
    recruiter_id: UUID | None = None
    headcount: int | None = Field(default=None, ge=1, le=10000)
    justification: str | None = Field(default=None, min_length=1, max_length=10000)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=240)
    country_code: Literal["GB","US","IN","AU"] | None = None
    employment_type: str | None = Field(default=None, max_length=80)
    work_mode: str | None = Field(default=None, max_length=40)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    required_skills: list[str] | None = Field(default=None, max_length=100)
    target_start_date: date | None = None
    target_close_date: date | None = None

    @field_validator("title", "justification")
    @classmethod
    def trim_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_ranges(self):
        values = self.model_dump(exclude_unset=True)
        if values.get("budget_min") is not None and values.get("budget_max") is not None and values["budget_max"] < values["budget_min"]:
            raise ValueError("budget_max must be greater than or equal to budget_min")
        if values.get("salary_min") is not None and values.get("salary_max") is not None and values["salary_max"] < values["salary_min"]:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        if values.get("target_start_date") and values.get("target_close_date") and values["target_close_date"] < values["target_start_date"]:
            raise ValueError("target_close_date cannot be earlier than target_start_date")
        return self

class RequisitionOut(RequisitionFields):
    id: UUID
    organization_id: UUID
    requisition_code: str
    requested_by: UUID
    status: RequisitionStatus
    submitted_at: datetime | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    rejected_by: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    approval_comment: str | None = None
    job_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
