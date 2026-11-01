"""Migration 024 integration tests. CI-only; never run against hosted databases."""
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from app.db import DatabaseConnectionError, get_connection


def safe_ci_database():
    parsed = urlparse(os.getenv("DATABASE_URL", ""))
    return (
        os.getenv("ATS_INTEGRATION_TESTS") == "1"
        and os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("CI") == "true"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.path.lstrip("/") == "ats_test"
    )


@unittest.skipUnless(os.getenv("ATS_INTEGRATION_TESTS") == "1", "Disposable PostgreSQL CI only")
class RecruiterTaskTenantMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not safe_ci_database():
            raise RuntimeError("Refusing non-disposable PostgreSQL database")
        migration = Path(__file__).resolve().parents[2] / "supabase/migrations/024_recruiter_tasks_tenant_integrity.sql"
        cls.sql = migration.read_text(encoding="utf-8")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("create table if not exists public.organizations (id uuid primary key)")
                cur.execute("""create table if not exists public.candidates (
                    id uuid primary key, organization_id uuid not null,
                    first_name text not null default 'Integration')""")
                cur.execute("""create table if not exists public.jobs (
                    id uuid primary key, organization_id uuid not null,
                    title text not null default 'Integration role')""")
                cur.execute("""create table if not exists public.recruiter_tasks (
                    id uuid primary key default gen_random_uuid(),
                    organization_id uuid not null references public.organizations(id) on delete cascade,
                    candidate_id uuid references public.candidates(id) on delete cascade,
                    job_id uuid references public.jobs(id) on delete set null)""")

        cls.org_a, cls.org_b = uuid4(), uuid4()
        cls.candidate_a, cls.job_a = uuid4(), uuid4()
        cls.bad_task = uuid4()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("insert into public.organizations (id) values (%s), (%s)", [cls.org_a, cls.org_b])
                cur.execute("insert into public.candidates (id, organization_id, first_name) values (%s, %s, %s)", [cls.candidate_a, cls.org_a, "Integration"])
                cur.execute("insert into public.jobs (id, organization_id, title) values (%s, %s, %s)", [cls.job_a, cls.org_a, "Integration role"])
                cur.execute(
                    "insert into public.recruiter_tasks (id, organization_id, candidate_id) values (%s, %s, %s)",
                    [cls.bad_task, cls.org_b, cls.candidate_a],
                )

        with unittest.TestCase().assertRaises(DatabaseConnectionError):
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(cls.sql)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.recruiter_tasks where id=%s", [cls.bad_task])
                cur.execute(
                    "insert into public.recruiter_tasks (id, organization_id, job_id) values (%s, %s, %s)",
                    [cls.bad_task, cls.org_b, cls.job_a],
                )

        with unittest.TestCase().assertRaises(DatabaseConnectionError):
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(cls.sql)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.recruiter_tasks where id=%s", [cls.bad_task])
                cur.execute(cls.sql)

    def setUp(self):
        self.org_a, self.org_b = uuid4(), uuid4()
        self.candidate, self.job, self.task = uuid4(), uuid4(), uuid4()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("insert into public.organizations (id) values (%s), (%s)", [self.org_a, self.org_b])
                cur.execute("insert into public.candidates (id, organization_id, first_name) values (%s, %s, %s)", [self.candidate, self.org_a, "Integration"])
                cur.execute("insert into public.jobs (id, organization_id, title) values (%s, %s, %s)", [self.job, self.org_a, "Integration role"])

    def tearDown(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.recruiter_tasks where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cur.execute("delete from public.candidates where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cur.execute("delete from public.jobs where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cur.execute("delete from public.organizations where id in (%s, %s)", [self.org_a, self.org_b])

    def test_same_tenant_references_are_allowed(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into public.recruiter_tasks (id, organization_id, candidate_id, job_id) values (%s, %s, %s, %s)",
                    [self.task, self.org_a, self.candidate, self.job],
                )

    def test_cross_tenant_candidate_is_rejected(self):
        with self.assertRaises(DatabaseConnectionError):
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.recruiter_tasks (id, organization_id, candidate_id) values (%s, %s, %s)",
                        [self.task, self.org_b, self.candidate],
                    )

    def test_cross_tenant_job_is_rejected(self):
        with self.assertRaises(DatabaseConnectionError):
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.recruiter_tasks (id, organization_id, job_id) values (%s, %s, %s)",
                        [self.task, self.org_b, self.job],
                    )

    def test_candidate_delete_cascades_task(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into public.recruiter_tasks (id, organization_id, candidate_id) values (%s, %s, %s)",
                    [self.task, self.org_a, self.candidate],
                )
                cur.execute("delete from public.candidates where id=%s", [self.candidate])
                cur.execute("select id from public.recruiter_tasks where id=%s", [self.task])
                self.assertIsNone(cur.fetchone())

    def test_job_delete_nulls_reference_and_keeps_task(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into public.recruiter_tasks (id, organization_id, job_id) values (%s, %s, %s)",
                    [self.task, self.org_a, self.job],
                )
                cur.execute("delete from public.jobs where id=%s", [self.job])
                cur.execute("select id, job_id from public.recruiter_tasks where id=%s", [self.task])
                row = cur.fetchone()
                self.assertIsNotNone(row)
                self.assertIsNone(row["job_id"])


if __name__ == "__main__":
    unittest.main()
