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
            support_case_id="44444444-4444-4444-8444-444444444444",
            purpose="Investigate the reported billing screen error",
            scope=["case_metadata", "case_messages"],
            duration_minutes=30,
        )
        self.assertLessEqual(request.duration_minutes, 60)
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                organization_id="11111111-1111-4111-8111-111111111111",
                support_case_id="44444444-4444-4444-8444-444444444444",
                purpose="Investigate issue",
                scope=["candidate_records"],
                duration_minutes=30,
            )

    def test_support_access_duration_cannot_exceed_one_hour(self):
        with self.assertRaises(ValidationError):
            SupportAccessRequest(
                organization_id="11111111-1111-4111-8111-111111111111",
                support_case_id="44444444-4444-4444-8444-444444444444",
                purpose="Investigate a reported service issue",
                scope=["case_metadata"],
                duration_minutes=120,
            )


class PlatformSupportQueuePrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_unapproved_queue_does_not_return_case_subject(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from app.routers import platform_ops
        from uuid import UUID

        class Cursor:
            def __init__(self):
                self.sql = ""
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, sql, params=None):
                self.sql = " ".join(sql.split())
            def fetchall(self):
                return [{
                    "id": UUID("44444444-4444-4444-8444-444444444444"),
                    "organization_id": UUID("11111111-1111-4111-8111-111111111111"),
                    "category": "privacy",
                    "priority": "normal",
                    "status": "open",
                    "assigned_operator_id": None,
                    "created_at": None,
                    "updated_at": None,
                }]

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def cursor(self):
                return cursor

        @contextmanager
        def fake_connection():
            with Connection() as connection:
                yield connection

        with patch.object(platform_ops, "assert_platform_operator"), patch.object(
            platform_ops, "get_connection", fake_connection
        ):
            result = await platform_ops.platform_list_support_cases()

        self.assertEqual(len(result["cases"]), 1)
        self.assertNotIn("subject", result["cases"][0])
        select_clause = cursor.sql.split(" from public.support_cases", 1)[0].lower()
        self.assertNotIn("subject", select_clause)


if __name__ == "__main__":
    unittest.main()
