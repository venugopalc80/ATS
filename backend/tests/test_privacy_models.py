from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.privacy import ProcessingRecordCreate, PrivacyRequestUpdate


def base_processing_record(**overrides):
    payload = {
        "organization_id": str(uuid4()),
        "candidate_id": str(uuid4()),
        "purpose": "recruitment",
        "legal_basis": "legitimate_interests",
    }
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
            legal_basis="contract",
            consent_status="granted",
            consent_captured_at=datetime.now(timezone.utc).isoformat(),
        ))


def test_withdrawn_consent_requires_withdrawal_timestamp():
    with pytest.raises(ValidationError, match="withdrawal timestamp"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="consent",
            consent_status="withdrawn",
            consent_captured_at=datetime.now(timezone.utc).isoformat(),
        ))


def test_withdrawal_cannot_predate_capture():
    with pytest.raises(ValidationError, match="cannot predate"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="consent",
            consent_status="withdrawn",
            consent_captured_at="2026-01-02T00:00:00+00:00",
            consent_withdrawn_at="2026-01-01T00:00:00+00:00",
        ))


@pytest.mark.parametrize("status", ["partially_completed", "declined"])
def test_partial_or_declined_request_requires_documented_exception(status):
    with pytest.raises(ValidationError):
        PrivacyRequestUpdate(status=status)
    accepted = PrivacyRequestUpdate(status=status, exception_details="Records retained under documented legal requirement")
    assert accepted.status == status
