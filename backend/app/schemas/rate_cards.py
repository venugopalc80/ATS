from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

EmploymentType = Literal["permanent", "contract", "temporary"]
RateBasis = Literal["hourly", "daily", "annual_salary", "fixed_fee", "percentage_fee"]
RateCardStatus = Literal["draft", "active", "expired", "archived"]


class RateCardCreate(BaseModel):
    organization_id: UUID
    client_id: UUID
    job_id: UUID | None = None
    name: str = Field(min_length=2, max_length=200)
    employment_type: EmploymentType
    rate_basis: RateBasis
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    rate_amount: Decimal | None = Field(default=None, ge=0)
    fee_percentage: Decimal | None = Field(default=None, gt=0, le=100)
    effective_from: date
    effective_to: date | None = None
    status: Literal["draft"] = "draft"
    notes: str | None = None


class RateCardUpdate(BaseModel):
    job_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=200)
    employment_type: EmploymentType | None = None
    rate_basis: RateBasis | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    rate_amount: Decimal | None = Field(default=None, ge=0)
    fee_percentage: Decimal | None = Field(default=None, gt=0, le=100)
    effective_from: date | None = None
    effective_to: date | None = None
    status: RateCardStatus | None = None
    notes: str | None = None


class RateCardOut(BaseModel):
    id: UUID
    organization_id: UUID
    client_id: UUID
    job_id: UUID | None
    name: str
    employment_type: EmploymentType
    rate_basis: RateBasis
    currency: str
    rate_amount: Decimal | None
    fee_percentage: Decimal | None
    effective_from: date
    effective_to: date | None
    status: RateCardStatus
    version: int
    notes: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
