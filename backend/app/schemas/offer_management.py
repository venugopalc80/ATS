from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfferApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected", "changes_requested"]
    comments: str | None = Field(default=None, max_length=4000)

    @field_validator("comments")
    @classmethod
    def normalize_comments(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class OfferCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: Literal["accepted", "declined"]
    evidence_reference: str = Field(min_length=1, max_length=1000)

    @field_validator("evidence_reference")
    @classmethod
    def require_evidence_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Record the candidate response evidence reference")
        return value


class OfferVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    offer_id: UUID
    version_number: int
    terms: dict
    terms_sha256: str
    created_by: UUID | None = None
    created_at: datetime
    issued_at: datetime | None = None
    document_storage_path: str | None = None
    document_sha256: str | None = None


class OfferApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    offer_id: UUID
    offer_version_id: UUID
    approver_id: UUID
    decision: Literal["approved", "rejected", "changes_requested"]
    comments: str | None = None
    decided_at: datetime
