"""HTTP authorization checks using real tenant membership rows in disposable PostgreSQL.

The application lookup is mocked to isolate the membership boundary. These tests do not
use live Supabase JWT validation or claim full production database integration coverage.
"""
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth import get_current_user_id
from app.main import app
from app.routers import applications


ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("99999999-9999-4999-8999-999999999999")
ACTOR = UUID("22222222-2222-4222-8222-222222222222")
RECRUITER = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
APPLICATION = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
JOB = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CANDIDATE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
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

    def test_real_membership_query_blocks_cross_tenant_read_and_transition(self):
        self.current_user["id"] = str(ACTOR)
        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            return_value=self._application_row(),
        ):
            response = self.client.get(f"/api/applications/{APPLICATION}")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("confidential recruiter assessment", response.text)

        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            return_value=self._application_row(),
        ):
            with patch.object(
                applications.service, "transition_application", new_callable=AsyncMock
            ) as transition:
                response = self.client.post(
                    f"/api/applications/{APPLICATION}/transition",
                    json={"status": "screening", "reason": "CV reviewed"},
                )
        self.assertEqual(response.status_code, 403)
        transition.assert_not_awaited()

    def test_real_membership_role_blocks_recruiter_stage_config_write(self):
        self.current_user["id"] = str(RECRUITER)
        with patch.object(
            applications.service, "update_stage_config", new_callable=AsyncMock
        ) as update_stage:
            response = self.client.patch(
                f"/api/applications/stages/screening?organization_id={ORG}",
                json={"label": "Private review"},
            )
        self.assertEqual(response.status_code, 403)
        update_stage.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
