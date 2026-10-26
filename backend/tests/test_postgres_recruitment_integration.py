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
    # Require GitHub Actions explicitly: a developer's local ats_test database
    # must never be modified merely because the opt-in flag was set.
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("CI") != "true":
        raise RuntimeError("Integration tests may run only in the disposable GitHub Actions service")
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
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null,
                        client_id uuid,
                        job_code text,
                        title text not null,
                        description text,
                        location text,
                        country_code text,
                        employment_type text,
                        work_mode text,
                        salary_min numeric,
                        salary_max numeric,
                        salary_currency char(3),
                        experience_min integer,
                        experience_max integer,
                        work_authorization text,
                        required_skills text[] not null default '{}',
                        preferred_skills text[] not null default '{}',
                        status text not null default 'draft',
                        recruiter_id uuid,
                        hiring_manager_id uuid,
                        created_by uuid,
                        closed_at timestamptz,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now()
                    )
                """)
                cursor.execute("""
                    create table if not exists public.job_requisitions (
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null,
                        requisition_code text not null,
                        title text not null,
                        department text,
                        client_id uuid,
                        requested_by uuid not null,
                        hiring_manager_id uuid,
                        recruiter_id uuid,
                        headcount integer not null default 1,
                        justification text not null,
                        budget_min numeric,
                        budget_max numeric,
                        location text,
                        country_code text,
                        employment_type text,
                        work_mode text,
                        salary_min numeric,
                        salary_max numeric,
                        salary_currency char(3),
                        required_skills text[] not null default '{}',
                        target_start_date date,
                        target_close_date date,
                        status text not null default 'draft',
                        submitted_at timestamptz,
                        approved_by uuid,
                        approved_at timestamptz,
                        rejected_by uuid,
                        rejected_at timestamptz,
                        rejection_reason text,
                        approval_comment text,
                        job_id uuid unique,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now(),
                        unique(organization_id, requisition_code)
                    )
                """)
                cursor.execute("""
                    create table if not exists public.audit_events (
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null,
                        actor_user_id uuid,
                        action text not null,
                        entity_type text not null,
                        entity_id uuid not null,
                        metadata jsonb not null default '{}'::jsonb,
                        created_at timestamptz not null default now()
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


    async def test_duplicate_active_application_is_rejected_without_creating_a_second_record(self):
        from fastapi import HTTPException

        email = f"{uuid4().hex}@example.test"
        payload = PublicApplicationIn(
            first_name="Duplicate",
            last_name="Candidate",
            email=email,
            consent=True,
            source="careers_page",
        )
        first = await apply_for_public_job(self.job_id, payload, self.organization_id)
        with self.assertRaises(HTTPException) as error:
            await apply_for_public_job(self.job_id, payload, self.organization_id)

        self.assertEqual(error.exception.status_code, 409)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) as total from public.applications where organization_id=%s and job_id=%s",
                    [self.organization_id, self.job_id],
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
                cursor.execute(
                    "select count(*) as total from public.candidates where organization_id=%s and lower(email)=lower(%s)",
                    [self.organization_id, email],
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
        self.assertTrue(first["success"])


class PostgreSQLRequisitionLifecycleIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the requisition lifecycle against the disposable PostgreSQL service."""

    def setUp(self):
        self.organization_id = uuid4()
        self.user_id = uuid4()

    async def _create_requisition(self):
        from app.schemas.requisitions import RequisitionCreate
        from app.services.requisition_service import RequisitionService

        payload = RequisitionCreate(
            organization_id=self.organization_id,
            title="Integration Platform Engineer",
            department="Engineering",
            justification="Database-backed lifecycle regression test",
            country_code="GB",
            employment_type="Permanent",
            work_mode="Hybrid",
            salary_min=Decimal("65000"),
            salary_max=Decimal("80000"),
            salary_currency="GBP",
            required_skills=["Python", "PostgreSQL"],
        )
        return await RequisitionService().create_requisition(payload, self.user_id)

    async def test_requisition_approval_conversion_and_retry_persist_in_postgres(self):
        from app.services.requisition_service import RequisitionService

        service = RequisitionService()
        created = await self._create_requisition()
        requisition_id = created["id"]
        self.assertEqual(created["status"], "draft")

        submitted = await service.submit(requisition_id, self.user_id)
        self.assertEqual(submitted["status"], "pending_approval")
        self.assertIsNotNone(submitted["submitted_at"])

        approved = await service.decide(requisition_id, self.user_id, True, "Budget approved")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval_comment"], "Budget approved")
        self.assertIsNotNone(approved["approved_at"])

        converted = await service.convert_to_job(requisition_id, self.user_id)
        self.assertFalse(converted["already_converted"])
        self.assertEqual(converted["requisition"]["status"], "converted")
        self.assertEqual(converted["job"]["title"], "Integration Platform Engineer")
        self.assertEqual(converted["job"]["status"], "draft")
        self.assertEqual(converted["job"]["job_code"], created["requisition_code"])

        retry = await service.convert_to_job(requisition_id, self.user_id)
        self.assertTrue(retry["already_converted"])
        self.assertEqual(retry["job"]["id"], converted["job"]["id"])

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select status, job_id from public.job_requisitions where id=%s",
                    [requisition_id],
                )
                persisted_req = cursor.fetchone()
                self.assertEqual(persisted_req["status"], "converted")
                self.assertEqual(persisted_req["job_id"], converted["job"]["id"])
                cursor.execute(
                    "select count(*) as total from public.jobs where organization_id=%s and job_code=%s",
                    [self.organization_id, created["requisition_code"]],
                )
                self.assertEqual(cursor.fetchone()["total"], 1)
                cursor.execute(
                    "select action from public.audit_events where entity_id=%s order by created_at",
                    [requisition_id],
                )
                actions = [row["action"] for row in cursor.fetchall()]
                self.assertEqual(
                    actions,
                    ["requisition.created", "requisition.submitted", "requisition.approved", "requisition.converted"],
                )
                cursor.execute(
                    "select count(*) as total from public.audit_events where action='job.created_from_requisition' and entity_id=%s",
                    [converted["job"]["id"]],
                )
                self.assertEqual(cursor.fetchone()["total"], 1)

    async def test_rejected_requisition_can_be_resubmitted_and_approved(self):
        from app.services.requisition_service import RequisitionService

        service = RequisitionService()
        created = await self._create_requisition()
        first_submission = await service.submit(created["id"], self.user_id)
        self.assertEqual(first_submission["status"], "pending_approval")

        rejected = await service.decide(created["id"], self.user_id, False, "Please clarify the headcount")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection_reason"], "Please clarify the headcount")
        self.assertIsNotNone(rejected["rejected_at"])

        resubmitted = await service.submit(created["id"], self.user_id)
        self.assertEqual(resubmitted["status"], "pending_approval")
        self.assertIsNone(resubmitted["rejection_reason"])
        self.assertIsNone(resubmitted["rejected_at"])

        approved = await service.decide(created["id"], self.user_id, True, "Clarification accepted")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval_comment"], "Clarification accepted")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select action from public.audit_events where entity_id=%s order by created_at",
                    [created["id"]],
                )
                actions = [row["action"] for row in cursor.fetchall()]
        self.assertEqual(
            actions,
            ["requisition.created", "requisition.submitted", "requisition.rejected",
             "requisition.submitted", "requisition.approved"],
        )


if __name__ == "__main__":
    unittest.main()
