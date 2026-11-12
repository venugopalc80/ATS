import pytest
from pydantic import ValidationError

from app.schemas.workflows import (
    WorkflowDefinitionPayload,
    WorkflowCondition,
    condition_matches,
    preview_workflow,
)


def definition(**overrides):
    value = {
        "name": "Interview reminders",
        "description": "Send a reminder after an interview is scheduled",
        "trigger_event": "interview.scheduled",
        "conditions": [{"field": "interview.status", "operator": "eq", "value": "scheduled"}],
        "steps": [
            {
                "key": "notify-interviewer",
                "action": "notify_interviewer_feedback_overdue",
                "conditions": [],
                "requires_approval": False,
                "config": {"template_key": "feedback-reminder"},
            }
        ],
    }
    value.update(overrides)
    return WorkflowDefinitionPayload.model_validate(value)


def test_condition_supports_nested_fields_and_safe_operators():
    assert condition_matches(
        WorkflowCondition(field="application.status", operator="eq", value="screening"),
        {"application": {"status": "screening"}},
    )
    assert not condition_matches(
        WorkflowCondition(field="application.status", operator="in", value=["offer", "hired"]),
        {"application": {"status": "screening"}},
    )


def test_preview_does_not_perform_side_effects():
    result = preview_workflow(
        definition(),
        "interview.scheduled",
        {"interview": {"status": "scheduled"}},
    )
    assert result["event_matches"] is True
    assert result["steps"][0]["would_run"] is True
    assert result["side_effects_performed"] is False


def test_preview_skips_when_event_does_not_match():
    result = preview_workflow(definition(), "application.created", {})
    assert result["event_matches"] is False
    assert result["steps"][0]["would_run"] is False


def test_workflow_step_keys_must_be_unique():
    with pytest.raises(ValidationError):
        definition(steps=[
            {"key": "same", "action": "create_interview_reminder"},
            {"key": "same", "action": "notify_interviewer_feedback_overdue"},
        ])


def test_unreviewed_offer_preparation_is_rejected():
    with pytest.raises(ValidationError):
        definition(steps=[
            {"key": "offer", "action": "prepare_offer_document_for_review", "requires_approval": False}
        ])


def test_automated_candidate_rejection_is_not_supported():
    with pytest.raises(ValidationError):
        definition(steps=[
            {"key": "reject", "action": "reject_candidate", "requires_approval": False}
        ])


def test_workflow_has_bounded_linear_step_count():
    with pytest.raises(ValidationError):
        definition(steps=[
            {"key": f"step-{i}", "action": "create_interview_reminder"}
            for i in range(21)
        ])
