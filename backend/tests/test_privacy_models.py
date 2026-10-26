import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers import privacy as privacy_module

from app.routers.privacy import (
    ProcessingRecordCreate, PrivacyRequestUpdate, RetentionPolicyCreate,
    retention_category_definition,
)


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


def test_privacy_request_can_record_supported_identity_verification_method():
    payload = PrivacyRequestUpdate(
        status="in_progress",
        identity_verification_method="email_challenge",
    )
    assert payload.identity_verification_method == "email_challenge"


def test_privacy_request_rejects_unknown_identity_verification_method():
    with pytest.raises(ValidationError):
        PrivacyRequestUpdate(
            status="in_progress",
            identity_verification_method="social_media_lookup",
        )



def test_retention_preview_uses_explicit_candidate_clock_and_allowlisted_table():
    definition = retention_category_definition("candidate_profile")
    assert definition is not None
    assert definition["table"] == "candidates"
    assert definition["target_table"] == "candidates"
    assert "retention_until" in definition["due_expression"]
    assert "created_at" in definition["clock_start"]


def test_retention_preview_supported_categories_have_fixed_table_mappings():
    document = retention_category_definition("candidate_document")
    processing_record = retention_category_definition("processing_record")
    assert document["table"] == "candidate_documents"
    assert processing_record["table"] == "candidate_processing_records"
    assert "r.candidate_id" in document["exception_match"]
    assert "r.candidate_id" in processing_record["exception_match"]


@pytest.mark.parametrize("category", ["audit_event", "application_record", "candidates; drop table candidates"])
def test_retention_preview_rejects_unconfigured_categories_without_sql_mapping(category):
    assert retention_category_definition(category) is None



def test_retention_preview_is_non_destructive_and_audits_access(monkeypatch):
    organization_id = uuid4()
    policy_id = uuid4()
    user_id = uuid4()
    preview_at = datetime(2026, 10, 22, tzinfo=timezone.utc)
    policy = {
        "id": policy_id,
        "data_category": "candidate_document",
        "purpose": "recruitment",
        "jurisdiction": "GB",
        "retention_days": 365,
        "action": "delete",
        "version": 1,
        "effective_at": preview_at,
    }
    item = {
        "id": uuid4(),
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "due_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    cursor_state = {"fetchall_calls": 0, "queries": []}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            cursor_state["queries"].append((query, params))

        def fetchall(self):
            cursor_state["fetchall_calls"] += 1
            if cursor_state["fetchall_calls"] == 1:
                return [policy]
            if cursor_state["fetchall_calls"] == 2:
                return [item]
            return []

        def fetchone(self):
            return {
                "held_count": 2,
                "processed_count": 1,
                "due_count": 3,
            }

    fake_cursor = FakeCursor()

    class FakeConnection:
        def cursor(self):
            return fake_cursor

    class FakeConnectionContext:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(privacy_module, "get_connection", lambda: FakeConnectionContext())
    monkeypatch.setattr(privacy_module, "assert_org_admin", lambda user, org: None)

    result = asyncio.run(privacy_module.preview_retention(
        organization_id=organization_id,
        policy_id=None,
        as_of=preview_at,
        limit=100,
        user_id=user_id,
    ))

    assert result["preview_only"] is True
    assert result["execution_enabled"] is False
    assert result["deletion_executed"] is False
    assert result["anonymisation_executed"] is False
    assert result["policies"][0]["due_count"] == 3
    assert result["policies"][0]["excluded_active_exception_count"] == 2
    assert result["policies"][0]["previously_processed_count"] == 1
    assert result["policies"][0]["items"] == [item]
    assert any("privacy.retention_previewed" in query for query, _ in cursor_state["queries"])
    assert any("e.target_table = 'candidates'" in query for query, _ in cursor_state["queries"])
    policy_query = cursor_state["queries"][0][0].lower()
    assert "distinct on (data_category, purpose, jurisdiction)" in policy_query
    assert "organization_id = %s" in policy_query
    assert "effective_at <= %s" in policy_query
    assert not any(query.lstrip().lower().startswith(("delete ", "update ")) for query, _ in cursor_state["queries"])


def test_retention_preview_rejects_naive_as_of_before_database_access(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(privacy_module, "assert_org_admin", lambda user, org: None)
    monkeypatch.setattr(
        privacy_module,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("database must not be accessed")),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_module.preview_retention(
            organization_id=uuid4(),
            policy_id=None,
            as_of=datetime(2026, 10, 22),
            limit=100,
            user_id=uuid4(),
        ))
    assert error.value.status_code == 422



def test_retention_exception_approval_cannot_be_self_approved(monkeypatch):
    from fastapi import HTTPException

    organization_id = uuid4()
    exception_id = uuid4()
    user_id = uuid4()
    state = {"queries": []}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            state["queries"].append((query, params))

        def fetchone(self):
            return {
                "organization_id": organization_id,
                "created_by": user_id,
                "approved_by": None,
                "exception_type": "manual_review",
            }

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeConnectionContext:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(privacy_module, "get_connection", lambda: FakeConnectionContext())
    monkeypatch.setattr(privacy_module, "assert_org_admin", lambda user, org: None)

    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_module.approve_retention_exception(
            exception_id=exception_id,
            user_id=user_id,
        ))

    assert error.value.status_code == 409
    assert "cannot approve their own" in error.value.detail
    assert not any("update public.retention_exceptions" in query.lower() for query, _ in state["queries"])



def test_retention_policy_rejects_timezone_naive_effective_at():
    with pytest.raises(ValidationError, match="must include a timezone"):
        RetentionPolicyCreate(
            organization_id=uuid4(), data_category="candidate_profile", purpose="recruitment",
            jurisdiction="GB", retention_days=365, action="review", version=1,
            effective_at=datetime(2026, 10, 22),
        )


def test_retention_exception_rejects_timezone_naive_clock():
    from app.routers.privacy import RetentionExceptionCreate

    with pytest.raises(ValidationError, match="starts_at must include a timezone"):
        RetentionExceptionCreate(
            organization_id=uuid4(), target_table="candidates", target_record_id=uuid4(),
            exception_type="legal_hold", reason="Active litigation hold",
            starts_at=datetime(2026, 10, 22),
        )


def test_retention_exception_rejects_end_before_start():
    from app.routers.privacy import RetentionExceptionCreate

    with pytest.raises(ValidationError, match="end must be after its start"):
        RetentionExceptionCreate(
            organization_id=uuid4(), target_table="candidates", target_record_id=uuid4(),
            exception_type="manual_review", reason="Manual review",
            starts_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        )



def test_notice_rejects_timezone_naive_effective_at():
    from app.routers.privacy import NoticeCreate

    with pytest.raises(ValidationError, match="effective_at must include a timezone"):
        NoticeCreate(
            organization_id=uuid4(), version="v1", purpose="recruitment",
            notice_text="Candidate privacy notice",
            effective_at=datetime(2026, 10, 25),
        )


def test_notice_rejects_blank_required_text():
    from app.routers.privacy import NoticeCreate

    with pytest.raises(ValidationError, match="must not be blank"):
        NoticeCreate(
            organization_id=uuid4(), version="  ", purpose="recruitment",
            notice_text="Candidate privacy notice",
            effective_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
        )


def test_retention_exception_rejects_blank_reason():
    from app.routers.privacy import RetentionExceptionCreate

    with pytest.raises(ValidationError, match="reason must not be blank"):
        RetentionExceptionCreate(
            organization_id=uuid4(), target_table="candidates", target_record_id=uuid4(),
            exception_type="manual_review", reason="   ",
            starts_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
        )


def test_consent_evidence_timestamps_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="consent_captured_at must include a timezone"):
        ProcessingRecordCreate(**base_processing_record(
            legal_basis="consent", consent_status="granted",
            consent_captured_at=datetime(2026, 10, 25),
        ))


def test_retention_policy_rejects_blank_category_and_purpose():
    for field_name, value in (("data_category", "   "), ("purpose", "  ")):
        payload = {
            "organization_id": uuid4(),
            "data_category": "candidate_profile",
            "purpose": "recruitment",
            "jurisdiction": "GB",
            "retention_days": 365,
            "action": "review",
            "version": 1,
            "effective_at": datetime(2026, 10, 26, tzinfo=timezone.utc),
        }
        payload[field_name] = value
        with pytest.raises(ValidationError, match="must not be blank"):
            RetentionPolicyCreate(**payload)


def test_processing_record_rejects_blank_purpose():
    payload = base_processing_record(legal_basis="legitimate_interests")
    payload["purpose"] = "   "
    with pytest.raises(ValidationError, match="purpose must not be blank"):
        ProcessingRecordCreate(**payload)



def test_privacy_request_concurrent_status_change_returns_conflict(monkeypatch):
    from fastapi import HTTPException

    organization_id = uuid4()
    request_id = uuid4()
    user_id = uuid4()
    state = {"queries": [], "update_attempted": False}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            state["queries"].append((query, params))
            if query.lstrip().lower().startswith("update public.privacy_rights_requests"):
                state["update_attempted"] = True

        def fetchone(self):
            last_query = state["queries"][-1][0].lstrip().lower()
            if last_query.startswith("select organization_id, status"):
                return {
                    "organization_id": organization_id,
                    "status": "received",
                    "identity_verified_at": None,
                    "identity_verified_by": None,
                    "identity_verification_method": None,
                }
            if last_query.startswith("update public.privacy_rights_requests"):
                # Simulate another request winning the conditional status update.
                return None
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    class FakeConnectionContext:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(privacy_module, "get_connection", lambda: FakeConnectionContext())
    monkeypatch.setattr(privacy_module, "assert_org_admin", lambda user, org: None)

    with pytest.raises(HTTPException) as error:
        asyncio.run(privacy_module.update_rights_request(
            request_id=request_id,
            payload=PrivacyRequestUpdate(status="identity_verification"),
            user_id=user_id,
        ))

    assert error.value.status_code == 409
    assert "changed while this update" in error.value.detail
    assert state["update_attempted"] is True
    assert not any("privacy.rights_request_status_changed" in query for query, _ in state["queries"])
