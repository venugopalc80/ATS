"""Opt-in PostgreSQL integration tests for the Careers -> Applications workflow.

These tests are enabled only in CI against the disposable `ats_test` database.
They deliberately refuse to run against hosted databases or any other database name.
"""
import os
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from app.db import get_connection
from app.routers.public_jobs import PublicApplicationIn, apply_for_public_job
from app.schemas.applications import ApplicationUpdate
from app.services.application_service import ApplicationService


def integration_database_is_safe() -> bool:
    if os.getenv("ATS_INTEGRATION_TESTS") != "1":
        return False
    url = os.getenv("DATABASE_URL", "")
    parsed = urlparse(url)
    # Fail closed: only the local disposable CI database is permitted.
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Integration tests refuse non-local PostgreSQL hosts")
    if parsed.path.lstrip("/") != "ats_test":
        raise RuntimeError("Integration tests require the disposable ats_test database")
    return True


@unittest.skipUnless(
    os.getenv("ATS_INTEGRATION_TESTS") == "1",
    "Set ATS_INTEGRATION_TESTS=1 only for the disposable local PostgreSQL CI service",
)
class PostgreSQLRecruitmentWorkflowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not integration_database_is_safe():
            raise RuntimeError("Unsafe integration-test database configuration")

        # This test suite runs in an empty, disposable CI database, never production.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    create table if not exists public.jobs (
                        id uuid primary key,
                        organization_id uuid not null,
                        title text not null,
                        description text,
                        location text,
                        country_code text,
                        employment_type text,
                        work_mode text,
                        salary_min numeric,
                        salary_max numeric,
                        salary_currency char(3),
                        required_skills text[] not null default '{}',
                        status text not null default 'draft',
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now()
                    )
                """)
                cursor.execute("""
                    create table if not exists public.candidates (
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null,
                        first_name text not null,
                        last_name text,
                        email text,
                        phone text,
                        status text not null default 'active',
                        consent_recorded_at timestamptz,
                        consent_purpose text,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now()
                    )
                """)
                cursor.execute("""
                    create table if not exists public.applications (
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null,
                        job_id uuid not null references public.jobs(id) on delete cascade,
                        candidate_id uuid not null references public.candidates(id) on delete cascade,
                        source text,
                        status text not null default 'new',
                        match_score numeric,
                        match_explanation text,
                        human_reviewed boolean not null default false,
                        human_reviewed_by uuid,
                        human_reviewed_at timestamptz,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now(),
                        unique(job_id, candidate_id)
                    )
                """)

    def setUp(self):
        self.organization_id = uuid4()
        self.other_organization_id = uuid4()
        self.job_id = uuid4()
        self.other_job_id = uuid4()
        self.user_id = uuid4()
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.jobs (id, organization_id, title, status) values (%s, %s, %s, 'open'), (%s, %s, %s, 'open')",
                    [self.job_id, self.organization_id, "Integration Test Role",
                     self.other_job_id, self.other_organization_id, "Other Tenant Role"],
                )

    def tearDown(self):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.applications where organization_id in (%s, %s)",
                    [self.organization_id, self.other_organization_id],
                )
                cursor.execute(
                    "delete from public.candidates where organization_id in (%s, %s)",
                    [self.organization_id, self.other_organization_id],
                )
                cursor.execute(
                    "delete from public.jobs where id in (%s, %s)",
                    [self.job_id, self.other_job_id],
                )

    async def test_careers_submission_is_persisted_and_visible_after_fresh_read(self):
        result = await apply_for_public_job(
            self.job_id,
            PublicApplicationIn(
                first_name="Integration",
                last_name="Candidate",
                email=f"{uuid4().hex}@example.test",
                consent=True,
                source="careers_page",
            ),
            self.organization_id,
        )
        application_id = result["application_id"]
        service = ApplicationService()

        first_read = await service.get_application(application_id)
        self.assertIsNotNone(first_read)
        self.assertEqual(first_read["organization_id"], self.organization_id)
        self.assertEqual(first_read["status"], "new")

        updated = await service.update_application(
            application_id, ApplicationUpdate(status="screening"), self.user_id
        )
        self.assertEqual(updated["status"], "screening")

        # A new query through the service proves the status was committed in PostgreSQL.
        after_reload = await ApplicationService().get_application(application_id)
        self.assertEqual(after_reload["status"], "screening")

    async def test_application_listing_is_scoped_to_requested_organization(self):
        result = await apply_for_public_job(
            self.job_id,
            PublicApplicationIn(
                first_name="Tenant",
                last_name="Boundary",
                email=f"{uuid4().hex}@example.test",
                consent=True,
            ),
            self.organization_id,
        )
        service = ApplicationService()
        own_rows = await service.list_applications(self.organization_id)
        other_rows = await service.list_applications(self.other_organization_id)

        self.assertIn(result["application_id"], [row["id"] for row in own_rows])
        self.assertEqual(other_rows, [])

    async def test_public_submission_cannot_apply_to_another_tenant_job(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as error:
            await apply_for_public_job(
                self.other_job_id,
                PublicApplicationIn(
                    first_name="Wrong",
                    last_name="Tenant",
                    email=f"{uuid4().hex}@example.test",
                    consent=True,
                ),
                self.organization_id,
            )
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
