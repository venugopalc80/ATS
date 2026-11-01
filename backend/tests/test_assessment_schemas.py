import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.assessments import (
    AssessmentAssignmentCreate,
    AssessmentResultCreate,
    AssessmentSubmissionCreate,
    AssessmentTemplateCreate,
    ProviderResultPayload,
)


class AssessmentSchemaTests(unittest.TestCase):
    def test_external_assessment_requires_provider(self):
        with self.assertRaises(ValidationError):
            AssessmentTemplateCreate(
                organization_id=uuid4(), name="Technical test", assessment_type="external_test",
                instructions="Complete the role-related exercise", role_requirements=["Python"],
            )

    def test_provider_is_not_accepted_for_internal_assessment(self):
        with self.assertRaises(ValidationError):
            AssessmentTemplateCreate(
                organization_id=uuid4(), name="Work sample", assessment_type="work_sample",
                instructions="Submit a short work sample", role_requirements=["Writing"],
                provider_key="vendor-x",
            )

    def test_provider_key_rejects_unicode_letters_and_punctuation(self):
        for provider_key in ("vendør", "vendor-x", "vendor.x", "vendor x"):
            with self.subTest(provider_key=provider_key):
                with self.assertRaises(ValidationError):
                    AssessmentTemplateCreate(
                        organization_id=uuid4(), name="External test", assessment_type="external_test",
                        instructions="Complete the role-related exercise", role_requirements=["Python"],
                        provider_key=provider_key,
                    )

    def test_provider_key_accepts_ascii_env_safe_name(self):
        template = AssessmentTemplateCreate(
            organization_id=uuid4(), name="External test", assessment_type="external_test",
            instructions="Complete the role-related exercise", role_requirements=["Python"],
            provider_key="vendor_2",
        )
        self.assertEqual(template.provider_key, "vendor_2")

    def test_template_requires_role_relevant_requirements_before_publish_flow(self):
        template = AssessmentTemplateCreate(
            organization_id=uuid4(), name="API exercise", assessment_type="technical_exercise",
            instructions="Build a small API", role_requirements=["Python", "API design"],
        )
        self.assertEqual(template.role_requirements, ["Python", "API design"])

    def test_deadline_must_include_timezone(self):
        with self.assertRaises(ValidationError):
            AssessmentAssignmentCreate(
                organization_id=uuid4(), application_id=uuid4(), template_id=uuid4(),
                due_at=datetime(2026, 11, 1, 12, 0),
            )

    def test_timezone_aware_deadline_is_accepted(self):
        assignment = AssessmentAssignmentCreate(
            organization_id=uuid4(), application_id=uuid4(), template_id=uuid4(),
            due_at=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(assignment.due_at.tzinfo, timezone.utc)

    def test_submission_requires_content_or_provider_reference(self):
        with self.assertRaises(ValidationError):
            AssessmentSubmissionCreate(submission_type="written_task")

    def test_score_and_max_score_must_be_consistent(self):
        with self.assertRaises(ValidationError):
            AssessmentResultCreate(source="human", methodology="Manual rubric", score=4)

    def test_score_cannot_exceed_max_score(self):
        with self.assertRaises(ValidationError):
            ProviderResultPayload(
                assignment_id=uuid4(), methodology="Provider rubric", score=6, max_score=5,
            )


if __name__ == "__main__":
    unittest.main()
