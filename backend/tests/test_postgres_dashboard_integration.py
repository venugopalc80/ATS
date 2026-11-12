"""Disposable-PostgreSQL integration test for the AQERITH dashboard aggregates."""
import os
import unittest
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import patch

from app.db import get_connection
from app.routers import dashboard as dashboard_router


def safe_database():
    if os.getenv("ATS_INTEGRATION_TESTS") != "1":
        return False
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("CI") != "true":
        raise RuntimeError("PostgreSQL integration tests may run only in GitHub Actions")
    parsed = urlparse(os.getenv("DATABASE_URL", ""))
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.path.lstrip("/") != "ats_test":
        raise RuntimeError("Refusing to run against anything except disposable local ats_test")
    return True


@unittest.skipUnless(os.getenv("ATS_INTEGRATION_TESTS") == "1", "Disposable PostgreSQL CI test only")
class DashboardPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not safe_database():
            raise RuntimeError("Unsafe PostgreSQL integration-test configuration")
        # Match all columns used by this endpoint and the existing recruitment
        # integration suite. No hosted database or customer records are involved.
        ddl = [
            """create table if not exists public.profiles (
                id uuid primary key, full_name text, email text)""",
            """create table if not exists public.organization_members (
                organization_id uuid not null, user_id uuid not null, role text not null default 'recruiter',
                primary key (organization_id, user_id))""",
            """create table if not exists public.clients (
                id uuid primary key, organization_id uuid not null, name text not null)""",
            """create table if not exists public.jobs (
                id uuid primary key, organization_id uuid not null, client_id uuid, job_code text, title text not null,
                description text, location text, country_code text, employment_type text, work_mode text,
                salary_min numeric, salary_max numeric, salary_currency char(3), experience_min numeric,
                experience_max numeric, work_authorization text, required_skills text[] not null default '{}',
                preferred_skills text[] not null default '{}', status text not null default 'draft',
                recruiter_id uuid, hiring_manager_id uuid, opened_at timestamptz, closed_at timestamptz,
                created_by uuid, created_at timestamptz not null default now(), updated_at timestamptz not null default now())""",
            """create table if not exists public.candidates (
                id uuid primary key default gen_random_uuid(), organization_id uuid not null, first_name text not null,
                last_name text, email text, phone text, city text, region text, country_code text,
                status text not null default 'active', current_title text, years_experience numeric,
                skills text[] not null default '{}', resume_path text, resume_text text, embedding text,
                ai_summary text, consent_recorded_at timestamptz, consent_purpose text, retention_until timestamptz,
                created_at timestamptz not null default now(), updated_at timestamptz not null default now())""",
            """create table if not exists public.applications (
                id uuid primary key default gen_random_uuid(), organization_id uuid not null, job_id uuid not null,
                candidate_id uuid not null, source text, status text not null default 'new', match_score numeric,
                match_explanation text, human_reviewed boolean not null default false, human_reviewed_by uuid,
                human_reviewed_at timestamptz, created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(), unique(job_id, candidate_id))""",
            """create table if not exists public.interviews (
                id uuid primary key, organization_id uuid not null, application_id uuid,
                scheduled_at timestamptz not null default now(), status text not null default 'scheduled', feedback text)""",
            """create table if not exists public.placements (
                id uuid primary key, organization_id uuid not null, status text not null default 'active',
                created_at timestamptz not null default now())""",
            """create table if not exists public.offers (
                id uuid primary key, organization_id uuid not null, application_id uuid, title text not null,
                expires_at timestamptz, status text not null default 'sent')""",
            """create table if not exists public.audit_events (
                id uuid primary key, organization_id uuid not null, action text not null, entity_type text not null,
                entity_id uuid, metadata jsonb not null default '{}', created_at timestamptz not null default now(),
                actor_user_id uuid)""",
        ]
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for statement in ddl:
                    cursor.execute(statement)

    async def test_aggregates_execute_and_exclude_other_organisations(self):
        org, other_org, recruiter = uuid4(), uuid4(), uuid4()
        job, other_job, candidate, other_candidate, application = (uuid4() for _ in range(5))
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("insert into public.profiles (id, full_name, email) values (%s,%s,%s)",
                                   [recruiter, "Integration Recruiter", "recruiter@example.test"])
                    cursor.execute("insert into public.organization_members (organization_id,user_id) values (%s,%s)",
                                   [org, recruiter])
                    cursor.execute(
                        """insert into public.jobs (id,organization_id,title,status,recruiter_id,required_skills)
                           values (%s,%s,'Python Engineer','open',%s,%s),(%s,%s,'Other Tenant Role','open',%s,%s)""",
                        [job, org, recruiter, ["Python", "SQL"], other_job, other_org, recruiter, ["Rust"]])
                    cursor.execute(
                        """insert into public.candidates (id,organization_id,first_name,status,skills)
                           values (%s,%s,'Own Candidate','active',%s),(%s,%s,'Other Candidate','active',%s)""",
                        [candidate, org, ["python"], other_candidate, other_org, ["Rust"]])
                    cursor.execute(
                        """insert into public.applications
                           (id,organization_id,job_id,candidate_id,status,updated_at)
                           values (%s,%s,%s,%s,'new',now())""", [application, org, job, candidate])

            with patch.object(dashboard_router, "assert_org_member"):
                result = await dashboard_router.dashboard(
                    organization_id=org, date_from=None, date_to=None, user_id=recruiter)

            self.assertEqual(len(result["team_workload"]), 1)
            self.assertEqual(result["team_workload"][0]["user_id"], str(recruiter))
            self.assertEqual(result["team_workload"][0]["open_vacancies"], 1)
            self.assertEqual(result["team_workload"][0]["active_applications"], 1)
            skills = {item["skill"].lower(): item for item in result["talent_intelligence"]}
            self.assertEqual(set(skills), {"python", "sql"})
            self.assertEqual(skills["python"]["active_candidates"], 1)
            self.assertEqual(skills["sql"]["active_candidates"], 0)
            self.assertEqual(skills["sql"]["gap"], 1)
        finally:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    for table, column in [
                        ("applications", "organization_id"), ("candidates", "organization_id"),
                        ("jobs", "organization_id"), ("organization_members", "organization_id")
                    ]:
                        cursor.execute(f"delete from public.{table} where {column} in (%s,%s)", [org, other_org])
                    cursor.execute("delete from public.profiles where id=%s", [recruiter])


if __name__ == "__main__":
    unittest.main()
