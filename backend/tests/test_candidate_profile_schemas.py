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
