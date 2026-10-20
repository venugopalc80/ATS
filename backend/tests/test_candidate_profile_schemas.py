import pytest
from pydantic import ValidationError

from app.schemas.candidate_profile import (
    CertificationBase,
    EmploymentBase,
    EducationBase,
    LanguageBase,
)


def test_employment_rejects_end_before_start():
    with pytest.raises(ValidationError):
        EmploymentBase(
            employer_name="Example Ltd",
            job_title="Engineer",
            start_date="2024-06-01",
            end_date="2023-06-01",
        )


def test_current_employment_cannot_have_end_date():
    with pytest.raises(ValidationError):
        EmploymentBase(
            employer_name="Example Ltd",
            job_title="Engineer",
            is_current=True,
            end_date="2025-01-01",
        )


def test_education_rejects_end_before_start():
    with pytest.raises(ValidationError):
        EducationBase(
            institution_name="Example University",
            start_date="2022-09-01",
            end_date="2021-06-01",
        )


def test_certification_rejects_expiry_before_issue():
    with pytest.raises(ValidationError):
        CertificationBase(
            name="Example certificate",
            issued_on="2025-01-01",
            expires_on="2024-01-01",
        )


def test_language_proficiency_is_limited_to_supported_values():
    with pytest.raises(ValidationError):
        LanguageBase(language="English", proficiency="expert")


def test_valid_profile_records_accept_normal_values():
    employment = EmploymentBase(
        employer_name="Example Ltd",
        job_title="Engineer",
        start_date="2024-01-01",
        is_current=True,
    )
    education = EducationBase(
        institution_name="Example University",
        qualification="MSc",
        field_of_study="Computer Science",
    )
    certification = CertificationBase(name="Cloud Fundamentals")
    language = LanguageBase(language="English", proficiency="fluent")

    assert employment.is_current is True
    assert education.qualification == "MSc"
    assert certification.name == "Cloud Fundamentals"
    assert language.proficiency == "fluent"


from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import candidate_profile


ORG_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CANDIDATE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def test_profile_route_denies_non_member_before_profile_database_access():
    with patch.object(candidate_profile, "_candidate_org", return_value=ORG_ID), \
         patch.object(candidate_profile, "assert_org_member", side_effect=HTTPException(status_code=403)), \
         patch.object(candidate_profile, "get_connection") as get_connection:
        with pytest.raises(HTTPException) as raised:
            candidate_profile._execute(
                CANDIDATE_ID,
                {"kind": "employment", "action": "list", "user_id": USER_ID},
            )

    assert raised.value.status_code == 403
    get_connection.assert_not_called()



from unittest.mock import MagicMock


def _profile_db_context():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    cursor_context.__exit__.return_value = False
    connection = MagicMock()
    connection.cursor.return_value = cursor_context
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    connection_context.__exit__.return_value = False
    return cursor, connection_context


def test_profile_update_scopes_record_lookup_to_candidate_and_organization():
    cursor, db_context = _profile_db_context()
    payload = EmploymentBase(employer_name="Example Ltd", job_title="Engineer")

    with patch.object(candidate_profile, "_candidate_org", return_value=ORG_ID), \
         patch.object(candidate_profile, "assert_org_member"), \
         patch.object(candidate_profile, "get_connection", return_value=db_context):
        with pytest.raises(HTTPException) as raised:
            candidate_profile._execute(
                CANDIDATE_ID,
                {
                    "kind": "employment",
                    "action": "update",
                    "user_id": USER_ID,
                    "record_id": UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                    "payload": payload,
                },
            )

    assert raised.value.status_code == 404
    query, params = cursor.execute.call_args.args
    assert "where id = %s and candidate_id = %s and organization_id = %s returning *" in query
    assert params[-2:] == [
        UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        CANDIDATE_ID,
        ORG_ID,
    ][-2:]


def test_profile_delete_scopes_record_lookup_to_candidate_and_organization():
    cursor, db_context = _profile_db_context()
    record_id = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")

    with patch.object(candidate_profile, "_candidate_org", return_value=ORG_ID), \
         patch.object(candidate_profile, "assert_org_member"), \
         patch.object(candidate_profile, "get_connection", return_value=db_context):
        with pytest.raises(HTTPException) as raised:
            candidate_profile._execute(
                CANDIDATE_ID,
                {
                    "kind": "employment",
                    "action": "delete",
                    "user_id": USER_ID,
                    "record_id": record_id,
                },
            )

    assert raised.value.status_code == 404
    query, params = cursor.execute.call_args.args
    assert "where id = %s and candidate_id = %s and organization_id = %s returning id" in query
    assert params == [record_id, CANDIDATE_ID, ORG_ID]



def test_missing_bearer_credentials_are_rejected():
    with pytest.raises(HTTPException) as raised:
        candidate_profile.get_current_user_id(None)
    assert raised.value.status_code == 401
    assert raised.value.detail == "Authentication required"
