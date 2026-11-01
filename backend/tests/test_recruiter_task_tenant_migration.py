"""Disposable-PostgreSQL integration coverage for migration 024.

The suite executes the repository migration itself against a fresh CI database.
It refuses hosted/non-CI database URLs and must never be pointed at staging or
production.
"""
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from app.db import get_connection


def safe_disposable_database() -> bool:
    if os.getenv("ATS_INTEGRATION_TESTS") != "1":
        return False
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("CI") != "true":
        raise RuntimeError("Integration tests may run only in disposable GitHub Actions PostgreSQL")
    parsed = urlparse(os.getenv("DATABASE_URL", ""))
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Refusing non-local PostgreSQL host")
    if parsed.path.lstrip("/") != "ats_test":
        raise RuntimeError("Refusing database other than ats_test")
    return True


@unittest.skipUnless(
    os.getenv("ATS_INTEGRATION_TESTS") == "1",
    "Requires the disposable PostgreSQL CI service",
)
class RecruiterTaskTenantMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not safe_disposable_database():
            raise RuntimeError("Unsafe integration-test database configuration")

        migration_path = (
            Path(__file__).resolve().parents[2]
            / "supabase"
            / "migrations"
            / "024_recruiter_tasks_tenant_integrity.sql"
        )
        cls.migration_sql = migration_path.read_text(encoding="utf-8")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    create table if not exists public.organizations (
                        id uuid primary key
                    )
                """)
                cursor.execute("""
                    create table if not exists public.candidates (
                        id uuid primary key,
                        organization_id uuid not null
                    )
                """)
                cursor.execute("""
                    create table if not exists public.jobs (
                        id uuid primary key,
                        organization_id uuid not null
                    )
                """)
                cursor.execute("""
                    create table if not exists public.recruiter_tasks (
                        id uuid primary key default gen_random_uuid(),
                        organization_id uuid not null references public.organizations(id) on delete cascade,
                        candidate_id uuid references public.candidates(id) on delete cascade,
                        job_id uuid references public.jobs(id) on delete set null
                    )
                """)

        # Prove the preflight rejects existing candidate and job tenant mismatches.
        cls.org_a, cls.org_b = uuid4(), uuid4()
        cls.candidate_a, cls.job_a = uuid4(), uuid4()
        cls.bad_candidate_task, cls.bad_job_task = uuid4(), uuid4()
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.organizations (id) values (%s), (%s)",
                    [cls.org_a, cls.org_b],
                )
                cursor.execute(
                    "insert into public.candidates (id, organization_id) values (%s, %s)",
                    [cls.candidate_a, cls.org_a],
                )
                cursor.execute(
                    "insert into public.jobs (id, organization_id) values (%s, %s)",
                    [cls.job_a, cls.org_a],
                )
                cursor.execute(
                    """insert into public.recruiter_tasks
                       (id, organization_id, candidate_id) values (%s, %s, %s)""",
                    [cls.bad_candidate_task, cls.org_b, cls.candidate_a],
                )
                with cls.assertRaisesContext_placeholder if False else _null_context():
                    pass

        # Execute failing preflight in its own transaction so the expected
        # exception rolls back only that transaction.
        with cls.assertRaisesDatabaseError():
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(cls.migration_sql)

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.recruiter_tasks where id=%s", [cls.bad_candidate_task])
                cursor.execute(
                    """insert into public.recruiter_tasks
                       (id, organization_id, job_id) values (%s, %s, %s)""",
                    [cls.bad_job_task, cls.org_b, cls.job_a],
                )

        with cls.assertRaisesDatabaseError():
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(cls.migration_sql)

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.recruiter_tasks where id=%s", [cls.bad_job_task])
                cursor.execute(cls.migration_sql)

    @classmethod
    def assertRaisesDatabaseError(cls):
        # psycopg errors are wrapped by get_connection as DatabaseConnectionError.
        from app.db import DatabaseConnectionError
        return unittest.TestCase().assertRaises(DatabaseConnectionError)

    def setUp(self):
        self.org_a, self.org_b = uuid4(), uuid4()
        self.candidate_a, self.job_a = uuid4(), uuid4()
        self.task_id = uuid4()
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.organizations (id), (id) values (%s), (%s)",
                    [self.org_a, self.org_b],
                )
                cursor.execute(
                    "insert into public.candidates (id, organization_id) values (%s, %s)",
                    [self.candidate_a, self.org_a],
                )
                cursor.execute(
                    "insert into public.jobs (id, organization_id) values (%s, %s)",
                    [self.job_a, self.org_a],
                )

    def tearDown(self):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.recruiter_tasks where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cursor.execute("delete from public.candidates where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cursor.execute("delete from public.jobs where organization_id in (%s, %s)", [self.org_a, self.org_b])
                cursor.execute("delete from public.organizations where id in (%s, %s)", [self.org_a, self.org_b])

    def test_same_organisation_candidate_and_job_references_are_allowed(self):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.recruiter_tasks
                       (id, organization_id, candidate_id, job_id)
                       values (%s, %s, %s, %s)""",
                    [self.task_id, self.org_a, self.candidate_a, self.job_a],
                )
                cursor.execute("select candidate_id, job_id from public.recruiter_tasks where id=%s", [self.task_id])
                row = cursor.fetchone()
                self.assertEqual(row["candidate_id"], self.candidate_a)
                self.assertEqual(row["job_id"], self.job_a)

    def test_cross_organisation_candidate_reference_is_rejected(self):
        with self.assertRaisesDatabaseError():
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """insert into public.recruiter_tasks
                           (id, organization_id, candidate_id)
                           values (%s, %s, %s)""",
                        [self.task_id, self.org_b, self.candidate_a],
                    )

    def test_cross_organisation_job_reference_is_rejected(self):
        with self.assertRaisesDatabaseError():
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """insert into public.recruiter_tasks
                           (id, organization_id, job_id)
                           values (%s, %s, %s)""",
                        [self.task_id, self.org_b, self.job_a],
                    )

    def test_deleting_candidate_cascades_task(self):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.recruiter_tasks (id, organization_id, candidate_id) values (%s, %s, %s)",
                    [self.task_id, self.org_a, self.candidate_a],
                )
                cursor.execute("delete from public.candidates where id=%s", [self.candidate_a])
                cursor.execute("select id from public.recruiter_tasks where id=%s", [self.task_id])
                self.assertIsNone(cursor.fetchone())

    def test_deleting_job_nulls_job_reference_and_preserves_task(self):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.recruiter_tasks (id, organization_id, job_id) values (%s, %s, %s)",
                    [self.task_id, self.org_a, self.job_a],
                )
                cursor.execute("delete from public.jobs where id=%s", [self.job_a])
                cursor.execute("select id, job_id from public.recruiter_tasks where id=%s", [self.task_id])
                row = cursor.fetchone()
                self.assertIsNotNone(row)
                self.assertIsNone(row["job_id"])


if __name__ == "__main__":
    unittest.main()
