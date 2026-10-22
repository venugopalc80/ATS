"""Validated request models for versioned interview kits and structured scorecards."""
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KitQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    evaluation_guidance: str | None = Field(default=None, max_length=2000)


class CompetencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    rating_guidance: dict[str, Any] = Field(default_factory=dict)
    questions: list[KitQuestionInput] = Field(default_factory=list, max_length=12)


class InterviewKitDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=4000)
    competencies: list[CompetencyInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_competencies(self):
        keys = [item.key for item in self.competencies]
        if len(keys) != len(set(keys)):
            raise ValueError("Competency keys must be unique within a template")
        return self


class InterviewKitCreate(InterviewKitDefinition):
    organization_id: UUID
    job_id: UUID | None = None


class ScorecardResponseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    competency_id: UUID
    rating: int = Field(ge=1, le=5)
    evidence: str = Field(min_length=1, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)


class InterviewFeedbackDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: UUID
    overall_summary: str | None = Field(default=None, max_length=4000)
    strengths: str | None = Field(default=None, max_length=4000)
    concerns: str | None = Field(default=None, max_length=4000)
    responses: list[ScorecardResponseInput] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_response_competencies(self):
        ids = [item.competency_id for item in self.responses]
        if len(ids) != len(set(ids)):
            raise ValueError("Each competency can have only one scorecard response")
        return self
