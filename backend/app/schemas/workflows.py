"""Validation primitives for AQERITH's declarative recruitment workflows.

Workflows are deliberately linear in v1: branching loops are not representable, and
the step count is capped to bound execution. Consequential actions require approval.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowEvent = Literal[
    "application.created",
    "application.stage_changed",
    "interview.scheduled",
    "interview.feedback_overdue",
    "offer.approved",
]

ALLOWED_ACTIONS = {
    "assign_vacancy_recruiter",
    "create_interview_reminder",
    "notify_interviewer_feedback_overdue",
    "prepare_offer_document_for_review",
    "send_approved_template",
    "request_human_approval",
}
HIGH_IMPACT_ACTIONS = {"prepare_offer_document_for_review", "send_approved_template"}
MAX_STEPS = 20
MAX_CONDITIONS = 10


class WorkflowCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=100)
    operator: Literal["eq", "neq", "in", "not_in", "exists"]
    value: Any = None


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    action: str
    conditions: list[WorkflowCondition] = Field(default_factory=list, max_length=MAX_CONDITIONS)
    requires_approval: bool = False
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self) -> "WorkflowStep":
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError("Unsupported workflow action")
        # Never permit an AI score or match score to drive an automated rejection.
        action_text = str(self.config.get("decision", "")).lower()
        if self.action == "reject_candidate" or action_text in {"reject", "auto_reject"}:
            raise ValueError("Automated candidate rejection is not supported")
        if self.action in HIGH_IMPACT_ACTIONS and not self.requires_approval:
            raise ValueError("This action must require human approval")
        return self


class WorkflowDefinitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    trigger_event: WorkflowEvent
    conditions: list[WorkflowCondition] = Field(default_factory=list, max_length=MAX_CONDITIONS)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="after")
    def validate_unique_steps(self) -> "WorkflowDefinitionPayload":
        keys = [step.key for step in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("Workflow step keys must be unique")
        return self


def _lookup(payload: dict[str, Any], dotted_key: str) -> Any:
    value: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def condition_matches(condition: WorkflowCondition, payload: dict[str, Any]) -> bool:
    actual = _lookup(payload, condition.field)
    if condition.operator == "exists":
        return actual is not None
    if condition.operator == "eq":
        return actual == condition.value
    if condition.operator == "neq":
        return actual != condition.value
    if condition.operator == "in":
        return isinstance(condition.value, list) and actual in condition.value
    if condition.operator == "not_in":
        return isinstance(condition.value, list) and actual not in condition.value
    return False


def workflow_matches(definition: WorkflowDefinitionPayload, event_name: str, payload: dict[str, Any]) -> bool:
    if definition.trigger_event != event_name:
        return False
    return all(condition_matches(condition, payload) for condition in definition.conditions)


def preview_workflow(definition: WorkflowDefinitionPayload, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    matches = workflow_matches(definition, event_name, payload)
    steps = []
    for step in definition.steps:
        passed = all(condition_matches(condition, payload) for condition in step.conditions)
        steps.append({
            "key": step.key,
            "action": step.action,
            "condition_matched": passed,
            "would_run": matches and passed,
            "requires_approval": step.requires_approval,
        })
    return {
        "event_matches": matches,
        "step_count": len(definition.steps),
        "steps": steps,
        "side_effects_performed": False,
        "note": "Preview validates routing only; no messages, records, or candidate decisions were changed.",
    }
