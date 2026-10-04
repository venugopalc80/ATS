from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
OfferStatus = Literal["draft","sent","accepted","rejected","withdrawn","expired"]
class OfferCreate(BaseModel):
    organization_id: UUID
    application_id: UUID
    title: str = Field(min_length=2,max_length=200)
    status: OfferStatus = "draft"
    employment_type: str | None = Field(default=None,max_length=50)
    start_date: date | None = None
    salary_amount: Decimal | None = Field(default=None,ge=0)
    salary_currency: str | None = Field(default=None,min_length=3,max_length=3)
    bonus_amount: Decimal | None = Field(default=None,ge=0)
    benefits: str | None = None
    expires_at: datetime | None = None
    notes: str | None = None
class OfferUpdate(BaseModel):
    title: str | None = Field(default=None,min_length=2,max_length=200)
    status: OfferStatus | None = None
    employment_type: str | None = Field(default=None,max_length=50)
    start_date: date | None = None
    salary_amount: Decimal | None = Field(default=None,ge=0)
    salary_currency: str | None = Field(default=None,min_length=3,max_length=3)
    bonus_amount: Decimal | None = Field(default=None,ge=0)
    benefits: str | None = None
    expires_at: datetime | None = None
    notes: str | None = None
class OfferOut(OfferCreate):
    id: UUID
    sent_at: datetime | None
    responded_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
