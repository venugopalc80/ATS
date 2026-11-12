import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from app.schemas.interviews import InterviewUpdate
from app.services.interview_service import InterviewService


INTERVIEW = UUID("77777777-7777-4777-8777-777777777777")
ACTOR = UUID("22222222-2222-4222-8222-222222222222")
ORIGINAL_AUTHOR = UUID("33333333-3333-4333-8333-333333333333")
ORIGINAL_TIME = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, feedback=None, author=ORIGINAL_AUTHOR, feedback_at=ORIGINAL_TIME):
        self.sql = ""
        self.params = []
        self.queries = []
        self.state = {
            "status": "scheduled",
            "feedback": feedback,
            "feedback_author_id": author,
            "feedback_at": feedback_at,
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if self.sql.startswith("select status, feedback from public.interviews"):
            return {"status": self.state["status"], "feedback": self.state["feedback"]}
        if self.sql.startswith("update public.interviews set"):
            if "feedback=%s" in self.sql:
                self.state["feedback"] = self.params[0]
            if "feedback_author_id=%s" in self.sql:
                author_index = self.sql.split(" where id=%s")[0].split(",").index("feedback_author_id=%s")
                self.state["feedback_author_id"] = self.params[author_index]
            if "feedback_at=now()" in self.sql:
                self.state["feedback_at"] = datetime(2026, 10, 15, 11, tzinfo=timezone.utc)
            elif "feedback_at=null" in self.sql:
                self.state["feedback_at"] = None
            return dict(self.state)
        raise AssertionError(f"Unexpected query: {self.sql}")


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class InterviewFeedbackAttributionTests(unittest.IsolatedAsyncioTestCase):
    async def test_changed_feedback_records_actor_and_database_timestamp(self):
        cursor = FakeCursor(feedback=None, author=None, feedback_at=None)

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.interview_service.get_connection", fake_connection):
            result = await InterviewService().update_interview(
                INTERVIEW, InterviewUpdate(feedback="Strong technical discussion"), ACTOR
            )

        update_sql, update_params = next(
            (sql, params) for sql, params in cursor.queries
            if sql.startswith("update public.interviews set")
        )
        self.assertIn("for update", cursor.queries[0][0])
        self.assertIn("feedback_author_id=%s", update_sql)
        self.assertIn("feedback_at=now()", update_sql)
        self.assertEqual(update_params[0], "Strong technical discussion")
        self.assertEqual(cursor.state["feedback_author_id"], ACTOR)
        self.assertIsNotNone(cursor.state["feedback_at"])
        self.assertEqual(result["feedback"], "Strong technical discussion")

    async def test_unchanged_feedback_does_not_reassign_author_or_timestamp(self):
        cursor = FakeCursor(feedback="Existing feedback")

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.interview_service.get_connection", fake_connection):
            await InterviewService().update_interview(
                INTERVIEW, InterviewUpdate(feedback="Existing feedback"), ACTOR
            )

        update_sql = next(
            sql for sql, _ in cursor.queries
            if sql.startswith("update public.interviews set")
        )
        self.assertNotIn("feedback_author_id=%s", update_sql)
        self.assertNotIn("feedback_at=now()", update_sql)

    async def test_clearing_feedback_clears_attribution(self):
        cursor = FakeCursor(feedback="Old feedback")

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.interview_service.get_connection", fake_connection):
            await InterviewService().update_interview(
                INTERVIEW, InterviewUpdate(feedback=""), ACTOR
            )

        update_sql = next(
            sql for sql, _ in cursor.queries
            if sql.startswith("update public.interviews set")
        )
        self.assertIn("feedback_author_id=%s", update_sql)
        self.assertIn("feedback_at=null", update_sql)
        self.assertIsNone(cursor.state["feedback_author_id"])
        self.assertIsNone(cursor.state["feedback_at"])


if __name__ == "__main__":
    unittest.main()
