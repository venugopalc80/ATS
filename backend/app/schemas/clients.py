from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

ClientStatus = Literal["prospect", "active", "inactive"]

class ClientBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: str | None = None
    industry: str | None = None
    country_code: Literal["GB", "US", "IN", "AU"] | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    status: ClientStatus = "prospect"

class ClientCreate(ClientBase):
    organization_id: UUID

class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    website: str | None = None
    industry: str | None = None
    country_code: Literal["GB", "US", "IN", "AU"] | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    status: ClientStatus | None = None

class ClientOut(ClientBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
