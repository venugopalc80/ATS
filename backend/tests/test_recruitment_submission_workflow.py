import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import public_jobs
from app.schemas.applications import ApplicationUpdate
from app.services.application_service import ApplicationService


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


class PublicApplyCursor:
    """Small SQL-aware fake: all state is in memory and no real database is touched."""

    def __init__(self):
        self.sql = ""
        self.params = []
        self.queries = []
        self.candidate_exists = False
        self.application_exists = False
        self.application_id = APPLICATION
        self.candidate_id = CANDIDATE

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if "select id from public.jobs" in self.sql:
            return {"id": JOB}
        if "select id from public.candidates" in self.sql:
            return {"id": CANDIDATE} if self.candidate_exists else None
        if "insert into public.candidates" in self.sql:
            self.candidate_exists = True
            return {"id": CANDIDATE}
        if "select id from public.applications" in self.sql:
            return {"id": APPLICATION} if self.application_exists else None
        if "insert into public.applications" in self.sql:
            self.application_exists = True
            return {"id": APPLICATION}
        raise AssertionError(f"Unexpected fetchone query: {self.sql}")


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class PublicCareersSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_submission_creates_candidate_and_new_application_in_requested_tenant(self):
        cursor = PublicApplyCursor()

        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection

        payload = public_jobs.PublicApplicationIn(
            first_name="Taylor",
            last_name="Candidate",
            email=" TAYLOR@example.com ",
            phone=None,
            consent=True,
            source="careers_page",
        )
        with patch.object(public_jobs, "get_connection", fake_connection):
            result = await public_jobs.apply_for_public_job(JOB, payload, ORG)

        self.assertEqual(result["application_id"], APPLICATION)
        self.assertTrue(result["success"])
        self.assertTrue(any("insert into public.candidates" in sql for sql, _ in cursor.queries))
        app_insert = next((sql, params) for sql, params in cursor.queries if "insert into public.applications" in sql)
        self.assertIn("'new'", app_insert[0])
        self.assertEqual(app_insert[1], [ORG, JOB, CANDIDATE, "careers_page"])
        self.assertEqual(
            next(params for sql, params in cursor.queries if "insert into public.candidates" in sql)[3],
            "taylor@example.com",
        )
        for sql, params in cursor.queries:
            if "organization_id" in sql:
                self.assertIn(ORG, params, f"Tenant scope missing from query: {sql}")

    async def test_public_submission_requires_consent_before_database_access(self):
        payload = public_jobs.PublicApplicationIn(
            first_name="Taylor",
            last_name="Candidate",
            email="taylor@example.com",
            consent=False,
            source="careers_page",
        )
        with patch.object(public_jobs, "get_connection") as connection:
            with self.assertRaises(HTTPException) as error:
                await public_jobs.apply_for_public_job(JOB, payload, ORG)
        self.assertEqual(error.exception.status_code, 422)
        connection.assert_not_called()

    async def test_duplicate_active_application_is_rejected(self):
        cursor = PublicApplyCursor()
        cursor.candidate_exists = True
        cursor.application_exists = True

        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection

        payload = public_jobs.PublicApplicationIn(
            first_name="Taylor",
            last_name="Candidate",
            email="taylor@example.com",
            consent=True,
            source="careers_page",
        )
        with patch.object(public_jobs, "get_connection", fake_connection):
            with self.assertRaises(HTTPException) as error:
                await public_jobs.apply_for_public_job(JOB, payload, ORG)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any("insert into public.applications" in sql for sql, _ in cursor.queries))


class ApplicationStagePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_update_is_written_and_visible_to_a_fresh_read(self):
        """Exercise the service's UPDATE then fresh SELECT contract using an isolated fake DB."""
        state = {
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
        executed = []

        class StateCursor:
            def __init__(self):
                self.sql = ""
                self.params = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                self.sql = " ".join(sql.split()).lower()
                self.params = params or []
                executed.append((self.sql, self.params))
                if self.sql.startswith("update public.applications set"):
                    state["status"] = self.params[0]
                    state["updated_at"] = NOW
                if self.sql.startswith("select set_config"):
                    return None

            def fetchone(self):
                if "select status from public.applications" in self.sql:
                    return {"status": state["status"]}
                if "from public.applications where id=%s" in self.sql:
                    return dict(state)
                if self.sql.startswith("update public.applications set"):
                    return dict(state)
                raise AssertionError(f"Unexpected fetchone query: {self.sql}")

        @contextmanager
        def fake_connection():
            with FakeConnection(StateCursor()) as connection:
                yield connection

        service = ApplicationService()
        with patch("app.services.application_service.get_connection", fake_connection):
            updated = await service.update_application(
                APPLICATION, ApplicationUpdate(status="screening"), USER
            )
            # A new service read simulates the Inbox being reloaded after refresh.
            after_refresh = await service.get_application(APPLICATION)

        self.assertEqual(updated["status"], "screening")
        self.assertEqual(after_refresh["status"], "screening")
        self.assertEqual(after_refresh["id"], APPLICATION)
        self.assertTrue(any(sql.startswith("update public.applications set") for sql, _ in executed))
        self.assertTrue(any("select set_config('app.actor_user_id'" in sql for sql, _ in executed))
        self.assertTrue(any("where organization_id = %s" in sql for sql, _ in executed) is False)  # ID lookup is followed by router membership checks.

    async def test_invalid_stage_transition_is_rejected_without_update(self):
        state = {"status": "new"}
        updates = []

        class StateCursor:
            def __init__(self):
                self.sql = ""
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, sql, params=None):
                self.sql = " ".join(sql.split()).lower()
                if self.sql.startswith("update public.applications set"):
                    updates.append(self.sql)
            def fetchone(self):
                if "select status from public.applications" in self.sql:
                    return dict(state)
                raise AssertionError(f"Unexpected query: {self.sql}")

        @contextmanager
        def fake_connection():
            with FakeConnection(StateCursor()) as connection:
                yield connection

        with patch("app.services.application_service.get_connection", fake_connection):
            with self.assertRaises(ValueError):
                await ApplicationService().update_application(
                    APPLICATION, ApplicationUpdate(status="hired"), USER
                )
        self.assertEqual(updates, [])


if __name__ == "__main__":
    unittest.main()
