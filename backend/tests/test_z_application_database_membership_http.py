"""HTTP authorization checks using real tenant membership rows in disposable PostgreSQL.

The application lookup is mocked to isolate the membership boundary. These tests do not
use live Supabase JWT validation or claim full production database integration coverage.
"""
import os
import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth import get_current_user_id
from app.main import app


ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("99999999-9999-4999-8999-999999999999")
ACTOR = UUID("22222222-2222-4222-8222-222222222222")
RECRUITER = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
APPLICATION = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
JOB = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CANDIDATE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_JOB = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
OTHER_CANDIDATE = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
NOW = "2026-10-14T12:00:00+00:00"


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "requires disposable PostgreSQL TEST_DATABASE_URL")
class ApplicationDatabaseMembershipHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
        cls.current_user = {"id": str(ACTOR)}
        app.dependency_overrides[get_current_user_id] = lambda: UUID(cls.current_user["id"])
        cls.client = TestClient(app)

        with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.organizations(id,name,country_code) values (%s,'Isolation test tenant','US') "
                    "on conflict (id) do nothing",
                    (OTHER_ORG,),
                )
                cursor.execute("insert into auth.users(id) values (%s) on conflict (id) do nothing", (RECRUITER,))
                cursor.execute("insert into public.profiles(id) values (%s) on conflict (id) do nothing", (RECRUITER,))
                cursor.execute(
                    "insert into public.organization_members(organization_id,user_id,role) values (%s,%s,'recruiter') "
                    "on conflict (organization_id,user_id) do update set role=excluded.role",
                    (ORG, RECRUITER),
                )
                cursor.execute(
                    "insert into public.jobs(id,organization_id) values (%s,%s) on conflict (id) do nothing",
                    (OTHER_JOB, OTHER_ORG),
                )
                cursor.execute(
                    "insert into public.candidates(id,organization_id) values (%s,%s) on conflict (id) do nothing",
                    (OTHER_CANDIDATE, OTHER_ORG),
                )
                cursor.execute(
                    "insert into public.candidates(id,organization_id,first_name) values (%s,%s,'Private Candidate') "
                    "on conflict (id) do nothing",
                    (OTHER_CANDIDATE, OTHER_ORG),
                )
                cursor.execute(
                    "insert into public.applications "
                    "(id,organization_id,job_id,candidate_id,source,status,match_explanation) "
                    "values (%s,%s,%s,%s,'careers_page','new','confidential recruiter assessment') "
                    "on conflict (id) do nothing",
                    (APPLICATION, OTHER_ORG, OTHER_JOB, OTHER_CANDIDATE),
                )
            connection.commit()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_current_user_id, None)
        if cls.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.previous_database_url

    def _application_row(self):
        return {
            "id": APPLICATION,
            "organization_id": OTHER_ORG,
            "job_id": JOB,
            "candidate_id": CANDIDATE,
            "source": "careers_page",
            "status": "new",
            "match_score": None,
            "match_explanation": "confidential recruiter assessment",
            "human_reviewed": False,
            "human_reviewed_by": None,
            "human_reviewed_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }

    def test_real_application_lookup_and_membership_block_cross_tenant_read_and_transition(self):
        # The route performs a real application SELECT and then a real membership
        # query. No application lookup or transition service method is mocked.
        self.current_user["id"] = str(ACTOR)
        response = self.client.get(f"/api/applications/{APPLICATION}")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("confidential recruiter assessment", response.text)

        response = self.client.post(
            f"/api/applications/{APPLICATION}/transition",
            json={"status": "screening", "reason": "CV reviewed"},
        )
        self.assertEqual(response.status_code, 403)

        import psycopg

        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status from public.applications where id=%s", (APPLICATION,))
                self.assertEqual(cursor.fetchone()[0], "new")

    def test_real_candidate_membership_query_hides_cross_tenant_candidate(self):
        # The candidate exists in PostgreSQL, but the caller is not a member
        # of its organisation. All candidate operations must conceal existence.
        self.current_user["id"] = str(ACTOR)

        response = self.client.get(f"/api/candidates/{OTHER_CANDIDATE}")
        self.assertEqual(response.status_code, 404)

        response = self.client.patch(
            f"/api/candidates/{OTHER_CANDIDATE}",
            json={"first_name": "Tampered"},
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.delete(f"/api/candidates/{OTHER_CANDIDATE}")
        self.assertEqual(response.status_code, 404)

        import psycopg

        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select first_name from public.candidates where id=%s",
                    (OTHER_CANDIDATE,),
                )
                self.assertEqual(cursor.fetchone()[0], "Private Candidate")

    def test_real_membership_role_blocks_recruiter_stage_config_write(self):
        # This uses the real membership row and real stage-config endpoint.
        self.current_user["id"] = str(RECRUITER)
        response = self.client.patch(
            f"/api/applications/stages/screening?organization_id={ORG}",
            json={"label": "Private review"},
        )
        self.assertEqual(response.status_code, 403)

        import psycopg

        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select label from public.application_stage_config "
                    "where organization_id=%s and stage_key='screening'",
                    (ORG,),
                )
                self.assertEqual(cursor.fetchone()[0], "Screening")


if __name__ == "__main__":
    unittest.main()
