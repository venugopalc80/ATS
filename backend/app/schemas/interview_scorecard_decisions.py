from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InterviewScorecardDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["proceed", "decline", "additional_interview", "hold"]
    rationale: str = Field(min_length=20, max_length=4000)
    evidence_response_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("rationale")
    @classmethod
    def rationale_must_be_meaningful(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 20:
            raise ValueError("Explain the decision with at least 20 characters of rationale")
        return value

    @field_validator("evidence_response_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Evidence references must be unique")
        return value
