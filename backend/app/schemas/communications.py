from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class ThreadCreate(BaseModel):
    organization_id: UUID
    application_id: UUID
    subject: str | None = Field(default=None, max_length=500)


class MessageDraftCreate(BaseModel):
    body_text: str = Field(min_length=1, max_length=20000)

    @field_validator("body_text")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message body cannot be blank")
        return value
    subject: str | None = Field(default=None, max_length=500)
    channel: str = Field(default="email", pattern="^(email|sms|in_app)$")
    recipient_address: str = Field(min_length=3, max_length=320)
    idempotency_key: str = Field(min_length=8, max_length=200)
    template_id: UUID | None = None
    template_version: int | None = Field(default=None, ge=1)


class InternalNoteCreate(BaseModel):
    body_text: str = Field(min_length=1, max_length=20000)

    @field_validator("body_text")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Note cannot be blank")
        return value


class TemplateCreate(BaseModel):
    organization_id: UUID
    template_key: str = Field(min_length=1, max_length=100, pattern="^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    channel: str = Field(pattern="^(email|sms|in_app)$")
    subject: str | None = Field(default=None, max_length=500)
    body_text: str = Field(min_length=1, max_length=20000)
