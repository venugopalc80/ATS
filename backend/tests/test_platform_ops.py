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

    async def test_platform_operator_cannot_read_case_without_active_approved_grant(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from uuid import UUID
        from fastapi import HTTPException
        from app.routers import platform_ops

        organization_id = UUID("11111111-1111-4111-8111-111111111111")
        case_id = UUID("44444444-4444-4444-8444-444444444444")

        class Cursor:
            def __init__(self):
                self.responses = [{"organization_id": organization_id}, None]
                self.executed = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, sql, params=None):
                self.executed.append((" ".join(sql.split()), params))
            def fetchone(self):
                return self.responses.pop(0) if self.responses else None

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
            with self.assertRaises(HTTPException) as raised:
                await platform_ops.platform_get_support_case(
                    case_id, user_id=UUID("99999999-9999-4999-8999-999999999999")
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(len(cursor.executed), 2)
        self.assertFalse(any("description" in sql.lower() for sql, _ in cursor.executed))

    async def test_expired_support_request_cannot_be_approved(self):
        from contextlib import contextmanager
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch
        from uuid import UUID
        from fastapi import HTTPException
        from app.routers import platform_ops

        organization_id = UUID("11111111-1111-4111-8111-111111111111")
        grant_id = UUID("66666666-6666-4666-8666-666666666666")

        class Cursor:
            def __init__(self):
                self.responses = [{
                    "organization_id": organization_id,
                    "approved_at": None,
                    "expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
                    "revoked_at": None,
                }, None]
                self.executed = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, sql, params=None):
                self.executed.append((" ".join(sql.split()), params))
            def fetchone(self):
                return self.responses.pop(0) if self.responses else None

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

        with patch.object(platform_ops, "get_connection", fake_connection), patch.object(
            platform_ops, "assert_org_admin"
        ):
            with self.assertRaises(HTTPException) as raised:
                await platform_ops.approve_support_access(
                    grant_id, user_id=UUID("99999999-9999-4999-8999-999999999999")
                )

        self.assertEqual(raised.exception.status_code, 409)
        update_sql = next(sql for sql, _ in cursor.executed if sql.lower().startswith("update public.support_access_grants"))
        self.assertIn("expires_at > now()", update_sql)
        self.assertEqual(len(cursor.executed), 2)

    async def test_support_message_access_denied_when_no_active_grant_matches(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from uuid import UUID
        from fastapi import HTTPException
        from app.routers import platform_ops

        organization_id = UUID("11111111-1111-4111-8111-111111111111")
        case_id = UUID("44444444-4444-4444-8444-444444444444")

        class Cursor:
            def __init__(self):
                self.responses = [{"organization_id": organization_id}, None]
                self.executed = []
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def execute(self, sql, params=None):
                self.executed.append((" ".join(sql.split()), params))
            def fetchone(self):
                return self.responses.pop(0) if self.responses else None

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
            with self.assertRaises(HTTPException) as raised:
                await platform_ops.platform_list_support_messages(
                    case_id, user_id=UUID("99999999-9999-4999-8999-999999999999")
                )

        self.assertEqual(raised.exception.status_code, 403)
        grant_sql = next(sql for sql, _ in cursor.executed if "from public.support_access_grants" in sql.lower())
        self.assertIn("approved_at is not null", grant_sql)
        self.assertIn("revoked_at is null", grant_sql)
        self.assertIn("expires_at > now()", grant_sql)
        self.assertFalse(any("from public.support_case_messages" in sql.lower() for sql, _ in cursor.executed))


if __name__ == "__main__":
    unittest.main()
