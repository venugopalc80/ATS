import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from app.schemas.applications import ApplicationUpdate
from app.services.application_service import ApplicationService


APPLICATION = UUID("33333333-3333-4333-8333-333333333333")
ACTOR = UUID("22222222-2222-4222-8222-222222222222")
FAKE_OTHER_USER = UUID("44444444-4444-4444-8444-444444444444")


class FakeCursor:
    def __init__(self, current_status="screening"):
        self.current_status = current_status
        self.sql = ""
        self.params = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if self.sql.lower().startswith("select status from public.applications"):
            return {"status": self.current_status}
        if self.sql.lower().startswith("update public.applications set"):
            return {"id": APPLICATION, "human_reviewed": True}
        return None


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class ApplicationReviewAttributionTests(unittest.IsolatedAsyncioTestCase):
    def test_client_cannot_supply_review_actor_or_timestamp(self):
        with self.assertRaises(ValidationError):
            ApplicationUpdate.model_validate({
                "human_reviewed": True,
                "human_reviewed_by": str(FAKE_OTHER_USER),
                "human_reviewed_at": "2026-01-01T00:00:00Z",
            })

    async def test_marking_reviewed_uses_authenticated_actor_and_database_time(self):
        cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.application_service.get_connection", fake_connection):
            await ApplicationService().update_application(
                APPLICATION, ApplicationUpdate(human_reviewed=True), ACTOR
            )

        update_sql, update_params = next(
            (sql, params) for sql, params in cursor.queries
            if sql.lower().startswith("update public.applications set")
        )
        self.assertIn("human_reviewed_by = %s", update_sql)
        self.assertIn("human_reviewed_at = now()", update_sql)
        self.assertIn(ACTOR, update_params)
        self.assertNotIn(FAKE_OTHER_USER, update_params)

    async def test_unmarking_review_clears_attribution(self):
        cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.application_service.get_connection", fake_connection):
            await ApplicationService().update_application(
                APPLICATION, ApplicationUpdate(human_reviewed=False), ACTOR
            )

        update_sql, update_params = next(
            (sql, params) for sql, params in cursor.queries
            if sql.lower().startswith("update public.applications set")
        )
        self.assertIn("human_reviewed_by = %s", update_sql)
        self.assertIn("human_reviewed_at = %s", update_sql)
        self.assertIn(None, update_params)


if __name__ == "__main__":
    unittest.main()
