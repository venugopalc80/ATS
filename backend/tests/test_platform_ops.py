import unittest
from pydantic import ValidationError

from app.routers.platform_ops import SupportAccessRequest, SupportCaseCreate


class SupportOperationsValidationTests(unittest.TestCase):
    def test_support_case_requires_valid_category_and_meaningful_description(self):
        payload = SupportCaseCreate(
            organization_id="11111111-1111-4111-8111-111111111111",
            category="technical",
            subject="Cannot create a job",
            description="The job form fails when I save it.",
        )
        self.assertEqual(payload.category, "technical")
        with self.assertRaises(ValidationError):
            SupportCaseCreate(
                organization_id="11111111-1111-4111-8111-111111111111",
                category="other",
                subject="Oops",
                description="short",
            )

    def test_support_access_is_time_limited_and_scope_bound(self):
        request = SupportAccessRequest(
            organization_id="11111111-1111-4111-8111-111111111111",
            purpose="Investigate the reported billing screen error",
            scope=["case_metadata", "subscription_metadata"],
            duration_minutes=30,
        )
        self.assertLessEqual(request.duration_minutes, 60)
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                organization_id="11111111-1111-4111-8111-111111111111",
                purpose="Investigate issue",
                scope=["candidate_records"],
                duration_minutes=30,
            )

    def test_support_access_duration_cannot_exceed_one_hour(self):
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                organization_id="11111111-1111-4111-8111-111111111111",
                purpose="Investigate a reported service issue",
                scope=["case_metadata"],
                duration_minutes=120,
            )


if __name__ == "__main__":
    unittest.main()
