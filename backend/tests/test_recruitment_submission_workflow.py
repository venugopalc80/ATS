import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import applications, public_jobs
from app.schemas.applications import ApplicationStageConfigUpdate, ApplicationTransition, ApplicationUpdate
from app.services.application_service import ApplicationService


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)

DEFAULT_STAGE_CONFIG = [
    {"stage_key": "new", "enabled": True, "allowed_next_stages": ["screening", "rejected", "withdrawn"]},
    {"stage_key": "screening", "enabled": True, "allowed_next_stages": ["shortlisted", "submitted", "interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "shortlisted", "enabled": True, "allowed_next_stages": ["interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "submitted", "enabled": True, "allowed_next_stages": ["interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "interview", "enabled": True, "allowed_next_stages": ["assessment", "offer", "rejected", "withdrawn"]},
    {"stage_key": "assessment", "enabled": True, "allowed_next_stages": ["interview", "offer", "rejected", "withdrawn"]},
    {"stage_key": "offer", "enabled": True, "allowed_next_stages": ["hired", "rejected", "withdrawn"]},
    {"stage_key": "hired", "enabled": True, "allowed_next_stages": []},
    {"stage_key": "rejected", "enabled": True, "allowed_next_stages": []},
    {"stage_key": "withdrawn", "enabled": True, "allowed_next_stages": []},
]


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
        candidate_update = next((sql, params) for sql, params in cursor.queries if "update public.candidates" in sql)
        self.assertIn("where id=%s and organization_id=%s", candidate_update[0])
        self.assertEqual(candidate_update[1][-1], ORG)


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
                if "select status, organization_id from public.applications" in self.sql:
                    return {"status": state["status"], "organization_id": state["organization_id"]}
                if "from public.applications where id=%s" in self.sql:
                    return dict(state)
                if self.sql.startswith("update public.applications set"):
                    return dict(state)
                raise AssertionError(f"Unexpected fetchone query: {self.sql}")

            def fetchall(self):
                if "from public.application_stage_config" in self.sql:
                    return list(DEFAULT_STAGE_CONFIG)
                return []

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
        # Tenant membership is enforced at the router boundary; service queries are ID-scoped.
        self.assertTrue(any("where id=%s" in sql for sql, _ in executed))

    async def test_invalid_stage_transition_is_rejected_without_update(self):
        state = {"status": "new", "organization_id": ORG}
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
                if "select status, organization_id from public.applications" in self.sql:
                    return dict(state)
                raise AssertionError(f"Unexpected query: {self.sql}")
            def fetchall(self):
                if "from public.application_stage_config" in self.sql:
                    return list(DEFAULT_STAGE_CONFIG)
                return []

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


class ApplicationRouterTenantAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_application_denies_non_member_before_returning_application(self):
        from fastapi import HTTPException

        row = {
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
        with patch.object(applications.service, "get_application", new_callable=AsyncMock, return_value=row):
            with patch.object(applications, "assert_org_member", side_effect=HTTPException(status_code=403, detail="Forbidden")):
                with self.assertRaises(HTTPException) as error:
                    await applications.get_application(APPLICATION, USER)

        self.assertEqual(error.exception.status_code, 403)

    async def test_update_application_does_not_mutate_before_membership_check(self):
        from fastapi import HTTPException

        row = {
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
        with patch.object(applications.service, "get_application", new_callable=AsyncMock, return_value=row):
            with patch.object(applications, "assert_org_member", side_effect=HTTPException(status_code=403, detail="Forbidden")):
                with patch.object(applications.service, "update_application", new_callable=AsyncMock) as update:
                    with self.assertRaises(HTTPException) as error:
                        await applications.update_application(
                            APPLICATION, ApplicationUpdate(status="screening"), USER
                        )

        self.assertEqual(error.exception.status_code, 403)
        update.assert_not_awaited()

    async def test_transition_application_denies_non_member_before_transition(self):
        row = {
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
        with patch.object(applications.service, "get_application", new_callable=AsyncMock, return_value=row):
            with patch.object(applications, "assert_org_member", side_effect=HTTPException(status_code=403, detail="Forbidden")):
                with patch.object(applications.service, "transition_application", new_callable=AsyncMock) as transition:
                    with self.assertRaises(HTTPException) as error:
                        await applications.transition_application(
                            APPLICATION,
                            ApplicationTransition(status="screening", reason="CV reviewed"),
                            USER,
                        )

        self.assertEqual(error.exception.status_code, 403)
        transition.assert_not_awaited()

    async def test_stage_config_update_requires_org_admin(self):
        with patch.object(applications, "assert_org_admin", side_effect=HTTPException(status_code=403, detail="Forbidden")):
            with patch.object(applications.service, "update_stage_config", new_callable=AsyncMock) as update:
                with self.assertRaises(HTTPException) as error:
                    await applications.update_application_stage(
                        "screening",
                        ORG,
                        ApplicationStageConfigUpdate(label="Screening"),
                        USER,
                    )

        self.assertEqual(error.exception.status_code, 403)
        update.assert_not_awaited()

    async def test_update_application_requires_transition_endpoint_for_status_changes(self):
        row = {
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
        with patch.object(applications.service, "get_application", new_callable=AsyncMock, return_value=row):
            with patch.object(applications, "assert_org_member"):
                with patch.object(applications.service, "update_application", new_callable=AsyncMock) as update:
                    with self.assertRaises(HTTPException) as error:
                        await applications.update_application(
                            APPLICATION, ApplicationUpdate(status="screening"), USER
                        )

        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("transition endpoint", error.exception.detail)
        update.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
