from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
class NoteCreate(BaseModel):
    organization_id: UUID
    candidate_id: UUID
    note: str = Field(min_length=1,max_length=10000)
class NoteOut(BaseModel):
    id: UUID
    organization_id: UUID
    candidate_id: UUID
    author_user_id: UUID | None = None
    note: str
    created_at: datetime
    updated_at: datetime
