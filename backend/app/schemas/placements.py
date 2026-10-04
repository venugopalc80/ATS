from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
PlacementStatus = Literal["pending","active","completed","cancelled"]
FeeType = Literal["fixed","percentage"]
class PlacementCreate(BaseModel):
    organization_id: UUID
    application_id: UUID
    offer_id: UUID | None = None
    job_id: UUID
    candidate_id: UUID
    client_id: UUID | None = None
    status: PlacementStatus = "pending"
    start_date: date
    end_date: date | None = None
    fee_amount: Decimal | None = Field(default=None,ge=0)
    fee_currency: str | None = Field(default=None,min_length=3,max_length=3)
    fee_type: FeeType | None = None
    fee_percentage: Decimal | None = Field(default=None,ge=0,le=100)
    notes: str | None = None
class PlacementUpdate(BaseModel):
    status: PlacementStatus | None = None
    offer_id: UUID | None = None
    client_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    fee_amount: Decimal | None = Field(default=None,ge=0)
    fee_currency: str | None = Field(default=None,min_length=3,max_length=3)
    fee_type: FeeType | None = None
    fee_percentage: Decimal | None = Field(default=None,ge=0,le=100)
    notes: str | None = None
class PlacementOut(PlacementCreate):
    id: UUID
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
