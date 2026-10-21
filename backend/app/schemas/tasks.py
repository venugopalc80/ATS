from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class TaskCreate(BaseModel):
    organization_id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    task_type: str = "task"
    priority: str = "normal"
    due_at: datetime | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None

    @model_validator(mode="after")
    def validate_task(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title cannot be blank")
        if self.task_type not in {"task", "candidate_follow_up"}:
            raise ValueError("task_type must be task or candidate_follow_up")
        if self.priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("invalid priority")
        if self.task_type == "candidate_follow_up" and self.candidate_id is None:
            raise ValueError("candidate_id is required for candidate_follow_up")
        return self

class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    priority: str | None = None
    due_at: datetime | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("title cannot be blank")
        if self.priority is not None and self.priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("invalid priority")
        if self.status is not None and self.status not in {"open", "completed", "cancelled"}:
            raise ValueError("status must be open, completed, or cancelled")
        return self

class TaskOut(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    description: str | None = None
    task_type: str
    status: str
    priority: str
    due_at: datetime | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None
    created_by: UUID
    completed_at: datetime | None = None
    completed_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
