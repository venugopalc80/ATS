import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from app.schemas.applications import ApplicationTransition
from app.services.application_service import ApplicationService


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 10, 22, 11, tzinfo=timezone.utc)


class StateCursor:
    def __init__(self, state):
        self.state = state
        self.sql = ""
        self.params = []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.params = params or []
        self.executed.append((self.sql, self.params))
        if self.sql.startswith("update public.applications set status="):
            self.state["status"] = self.params[0]
            self.state["updated_at"] = NOW

    def fetchone(self):
        if "select status from public.applications" in self.sql:
            return {"status": self.state["status"]}
        if "from public.applications where id=%s" in self.sql:
            return dict(self.state)
        if self.sql.startswith("update public.applications set status="):
            return dict(self.state)
        raise AssertionError(f"Unexpected fetchone query: {self.sql}")

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class ApplicationStageTransitionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {
            "id": APPLICATION,
            "organization_id": ORG,
            "job_id": JOB,
            "candidate_id": CANDIDATE,
            "source": "careers_page",
            "status": "new",
            "match_score": None,
            "match_explanation": None,
            "human_reviewed": False,
            "human_reviewed_by": None,
            "human_reviewed_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.cursor = StateCursor(self.state)

        @contextmanager
        def fake_connection():
            with FakeConnection(self.cursor) as connection:
                yield connection

        self.connection_patch = patch("app.services.application_service.get_connection", fake_connection)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    async def test_valid_transition_sets_actor_and_reason(self):
        result = await ApplicationService().transition_application(
            APPLICATION, "screening", USER, "CV reviewed"
        )
        self.assertEqual(result["status"], "screening")
        self.assertIn(
            ("select set_config('app.actor_user_id', %s, true)", [str(USER)]),
            self.cursor.executed,
        )
        self.assertIn(
            ("select set_config('app.transition_reason', %s, true)", ["CV reviewed"]),
            self.cursor.executed,
        )
        self.assertTrue(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    async def test_invalid_transition_is_rejected_without_update(self):
        with self.assertRaisesRegex(ValueError, "Invalid application stage transition"):
            await ApplicationService().transition_application(
                APPLICATION, "hired", USER, "Skip stages"
            )
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    async def test_same_stage_is_idempotent_and_does_not_write(self):
        self.state["status"] = "screening"
        result = await ApplicationService().transition_application(
            APPLICATION, "screening", USER, "No-op"
        )
        self.assertEqual(result["status"], "screening")
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))


if __name__ == "__main__":
    unittest.main()
