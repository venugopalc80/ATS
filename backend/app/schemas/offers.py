from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


OfferStatus = Literal[
    "draft", "awaiting_approval", "approved", "issued", "accepted", "declined",
    "expired", "withdrawn", "sent", "rejected",
]


class OfferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    application_id: UUID
    title: str = Field(min_length=2, max_length=200)
    # Kept for compatibility with existing clients; the service always creates drafts.
    status: OfferStatus = "draft"
    employment_type: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    salary_amount: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    bonus_amount: Decimal | None = Field(default=None, ge=0)
    benefits: str | None = Field(default=None, max_length=8000)
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("salary_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class OfferUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=2, max_length=200)
    status: OfferStatus | None = None
    employment_type: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    salary_amount: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    bonus_amount: Decimal | None = Field(default=None, ge=0)
    benefits: str | None = Field(default=None, max_length=8000)
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("salary_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class OfferOut(OfferCreate):
    id: UUID
    current_version: int = 1
    approved_at: datetime | None = None
    approved_by: UUID | None = None
    issued_at: datetime | None = None
    issued_by: UUID | None = None
    candidate_responded_at: datetime | None = None
    candidate_response: Literal["accepted", "declined"] | None = None
    withdrawn_at: datetime | None = None
    withdrawn_by: UUID | None = None
    sent_at: datetime | None = None
    responded_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
