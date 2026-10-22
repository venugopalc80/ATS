from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.privacy import ProcessingRecordCreate, PrivacyRequestUpdate, RetentionPolicyCreate


def base_processing_record(**overrides):
    payload = {"organization_id": str(uuid4()), "candidate_id": str(uuid4()),
               "purpose": "recruitment", "legal_basis": "legitimate_interests"}
    payload.update(overrides)
    return payload


def test_non_consent_legal_basis_does_not_require_consent():
    record = ProcessingRecordCreate(**base_processing_record())
    assert record.legal_basis == "legitimate_interests"
    assert record.consent_status is None


def test_consent_basis_requires_status_and_capture_timestamp():
    with pytest.raises(ValidationError, match="explicit status and capture timestamp"):
        ProcessingRecordCreate(**base_processing_record(legal_basis="consent"))


def test_non_consent_basis_rejects_granted_consent_flag():
    with pytest.raises(ValidationError, match="non-consent legal basis"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="contract", consent_status="granted",
            consent_captured_at=datetime.now(timezone.utc).isoformat()))


def test_withdrawn_consent_requires_withdrawal_timestamp():
    with pytest.raises(ValidationError, match="withdrawal timestamp"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="consent", consent_status="withdrawn",
            consent_captured_at=datetime.now(timezone.utc).isoformat()))


def test_withdrawal_cannot_predate_capture():
    with pytest.raises(ValidationError, match="cannot predate"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="consent", consent_status="withdrawn",
            consent_captured_at="2026-01-02T00:00:00+00:00",
            consent_withdrawn_at="2026-01-01T00:00:00+00:00"))


@pytest.mark.parametrize("status", ["partially_completed", "declined"])
def test_partial_or_declined_request_requires_documented_exception(status):
    with pytest.raises(ValidationError, match="documented exception"):
        PrivacyRequestUpdate(status=status)
    accepted = PrivacyRequestUpdate(status=status, exception_details="Records retained under documented legal requirement")
    assert accepted.status == status


def test_retention_policy_is_versioned_and_bounded():
    policy = RetentionPolicyCreate(
        organization_id=uuid4(), data_category="candidate_cv", purpose="recruitment",
        jurisdiction="GB", retention_days=365, action="review", version=1,
        effective_at=datetime(2026, 10, 22, tzinfo=timezone.utc))
    assert policy.version == 1
    assert policy.retention_days == 365


def test_retention_policy_rejects_negative_retention_period():
    with pytest.raises(ValidationError):
        RetentionPolicyCreate(
            organization_id=uuid4(), data_category="candidate_cv", purpose="recruitment",
            jurisdiction="GB", retention_days=-1, action="delete", version=1,
            effective_at=datetime(2026, 10, 22, tzinfo=timezone.utc))


from app.routers.privacy import is_privacy_request_transition_allowed


@pytest.mark.parametrize(
    ("current", "next_status"),
    [
        ("received", "identity_verification"),
        ("identity_verification", "in_progress"),
        ("in_progress", "completed"),
        ("awaiting_information", "in_progress"),
        ("partially_completed", "completed"),
        ("received", "cancelled"),
    ],
)
def test_privacy_request_allows_documented_transitions(current, next_status):
    assert is_privacy_request_transition_allowed(current, next_status)


@pytest.mark.parametrize(
    ("current", "next_status"),
    [
        ("received", "completed"),
        ("completed", "in_progress"),
        ("declined", "completed"),
        ("cancelled", "identity_verification"),
        ("awaiting_information", "declined"),
    ],
)
def test_privacy_request_rejects_invalid_transitions(current, next_status):
    assert not is_privacy_request_transition_allowed(current, next_status)


def test_privacy_request_can_keep_current_status():
    assert is_privacy_request_transition_allowed("in_progress", "in_progress")


def test_partial_completion_rejects_whitespace_only_justification():
    with pytest.raises(ValidationError, match="documented exception"):
        PrivacyRequestUpdate(status="partially_completed", exception_details="   ")
