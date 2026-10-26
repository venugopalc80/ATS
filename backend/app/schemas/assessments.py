from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator

AssessmentType = Literal["work_sample", "technical_exercise", "written_task", "external_test"]
TemplateStatus = Literal["draft", "published", "archived"]
AssignmentStatus = Literal["assigned", "in_progress", "submitted", "under_review", "completed", "cancelled", "expired", "provider_error"]
Recommendation = Literal["advance", "review", "not_recommended", "no_recommendation"]


class AssessmentTemplateCreate(BaseModel):
    organization_id: UUID
    job_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    assessment_type: AssessmentType
    instructions: str = Field(min_length=1, max_length=8000)
    evaluation_guidance: str | None = Field(default=None, max_length=8000)
    role_requirements: list[str] = Field(default_factory=list, max_length=40)
    accessibility_options: dict[str, Any] = Field(default_factory=dict)
    provider_key: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("provider_key")
    @classmethod
    def provider_key_must_be_env_safe(cls, value):
        if value is not None and (not value or any(not (("A" <= char <= "Z") or ("a" <= char <= "z") or ("0" <= char <= "9") or char == "_") for char in value)):
            raise ValueError("Provider key may contain only ASCII letters, numbers, and underscores")
        return value

    @model_validator(mode="after")
    def provider_for_external_only(self):
        if self.assessment_type == "external_test" and not self.provider_key:
            raise ValueError("External assessments require a provider key")
        if self.assessment_type != "external_test" and self.provider_key:
            raise ValueError("Provider key is only supported for external assessments")
        if any(not item.strip() or len(item) > 160 for item in self.role_requirements):
            raise ValueError("Role requirements must be non-empty and at most 160 characters")
        return self


class AssessmentTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, min_length=1, max_length=8000)
    evaluation_guidance: str | None = Field(default=None, max_length=8000)
    role_requirements: list[str] | None = Field(default=None, max_length=40)
    accessibility_options: dict[str, Any] | None = None
    status: Literal["draft", "archived"] | None = None


class AssessmentTemplateOut(BaseModel):
    id: UUID
    organization_id: UUID
    job_id: UUID | None
    name: str
    description: str | None
    assessment_type: AssessmentType
    instructions: str
    evaluation_guidance: str | None
    role_requirements: list[str]
    accessibility_options: dict[str, Any]
    provider_key: str | None
    status: TemplateStatus
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssessmentAssignmentCreate(BaseModel):
    organization_id: UUID
    application_id: UUID
    template_id: UUID
    due_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    accommodation_requested: bool = False
    accommodation_arrangements: str | None = Field(default=None, max_length=2000)

    @field_validator("due_at")
    @classmethod
    def deadline_must_be_timezone_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Deadline must include a timezone")
        return value


class AssessmentAssignmentUpdate(BaseModel):
    due_at: datetime | None = None
    extension_reason: str | None = Field(default=None, min_length=1, max_length=2000)
    accommodation_requested: bool | None = None
    accommodation_arrangements: str | None = Field(default=None, max_length=2000)
    status: Literal["cancelled"] | None = None

    @field_validator("due_at")
    @classmethod
    def extension_deadline_must_be_timezone_aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Deadline must include a timezone")
        return value


class AssessmentAssignmentOut(BaseModel):
    id: UUID
    organization_id: UUID
    application_id: UUID
    template_id: UUID
    status: AssignmentStatus
    assigned_by: UUID | None
    due_at: datetime | None
    extended_due_at: datetime | None
    extension_reason: str | None
    accommodation_requested: bool
    accommodation_arrangements: str | None
    instructions_snapshot: str
    provider_key: str | None
    provider_assignment_ref: str | None
    assigned_at: datetime
    started_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssessmentSubmissionCreate(BaseModel):
    submission_type: AssessmentType
    text_content: str | None = Field(default=None, max_length=100000)
    provider_submission_ref: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_evidence(self):
        if not (self.text_content and self.text_content.strip()) and not self.provider_submission_ref:
            raise ValueError("Provide submission content or a provider submission reference")
        return self


class AssessmentResultCreate(BaseModel):
    submission_id: UUID | None = None
    source: Literal["human", "system"]
    methodology: str = Field(min_length=1, max_length=2000)
    score: Decimal | None = Field(default=None, ge=0, le=1000000)
    max_score: Decimal | None = Field(default=None, gt=0, le=1000000)
    summary: str | None = Field(default=None, max_length=8000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    result_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_score_pair(self):
        if (self.score is None) != (self.max_score is None):
            raise ValueError("score and max_score must be provided together")
        if self.score is not None and self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        return self


class AssessmentReviewCreate(BaseModel):
    result_id: UUID | None = None
    feedback: str = Field(min_length=1, max_length=8000)
    recommendation: Recommendation = "review"


class ProviderResultPayload(BaseModel):
    assignment_id: UUID
    methodology: str = Field(min_length=1, max_length=2000)
    score: Decimal | None = Field(default=None, ge=0, le=1000000)
    max_score: Decimal | None = Field(default=None, gt=0, le=1000000)
    summary: str | None = Field(default=None, max_length=8000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    provider_result_ref: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_score_pair(self):
        if (self.score is None) != (self.max_score is None):
            raise ValueError("score and max_score must be provided together")
        if self.score is not None and self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        return self
