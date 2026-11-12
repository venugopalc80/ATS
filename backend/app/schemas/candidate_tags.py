from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
TagColour = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CandidateTagCreate(BaseModel):
    organization_id: UUID
    name: TagName
    colour: TagColour = "#64748b"


class CandidateTagOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    colour: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CandidateTagAssignmentOut(BaseModel):
    candidate_id: UUID
    tag_id: UUID
    organization_id: UUID
    assigned_by: UUID | None = None
    created_at: datetime
