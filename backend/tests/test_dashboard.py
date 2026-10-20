import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from uuid import UUID
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import dashboard as dashboard_router


ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
JOB = UUID("33333333-3333-4333-8333-333333333333")
INTERVIEW = UUID("44444444-4444-4444-8444-444444444444")
OFFER = UUID("55555555-5555-4555-8555-555555555555")


class FakeCursor:
    def __init__(self):
        self.sql = ""
        self.params = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if "from public.jobs where" in self.sql:
            return {"total": 2}
        if "from public.candidates where" in self.sql:
            return {"total": 8}
        if "from public.interviews where" in self.sql:
            return {"total": 1}
        if "from public.placements where" in self.sql and "date_trunc('month'" in self.sql:
            return {"total": 3}
        if "from public.placements where" in self.sql:
            return {"total": 4}
        if "from public.applications" in self.sql and "updated_at <" in self.sql:
            return {"total": 1}
        raise AssertionError(f"Unexpected fetchone query: {self.sql}")

    def fetchall(self):
        if "group by status" in self.sql:
            return [
                {"status": "new", "total": 2},
                {"status": "interview", "total": 1},
                {"status": "rejected", "total": 1},
            ]
        if "left join public.applications" in self.sql:
            return [{
                "id": JOB, "title": "Backend Engineer", "client": "Example Ltd",
                "status": "open", "applicants": 1, "days_open": 42,
            }]
        if "from public.interviews i" in self.sql and "scheduled_at" in self.sql and "limit 10" in self.sql:
            if "feedback is null" in self.sql:
                return [{
                    "id": INTERVIEW, "application_id": "app-1",
                    "scheduled_at": datetime(2026, 10, 13, 10, tzinfo=timezone.utc),
                    "status": "completed",
                }]
            return [{
                "id": INTERVIEW, "application_id": "app-1",
                "scheduled_at": datetime(2026, 10, 13, 10, tzinfo=timezone.utc),
                "status": "scheduled",
            }]
        if "from public.offers o" in self.sql:
            return [{
                "id": OFFER, "application_id": "app-2", "title": "Offer for Analyst",
                "expires_at": datetime(2026, 10, 14, 12, tzinfo=timezone.utc), "status": "sent",
            }]
        if "from public.organization_members om" in self.sql:
            return [{"user_id": USER, "name": "Recruiter", "open_vacancies": 2, "active_applications": 5, "overdue_decisions": 1}]
        if "with demand as" in self.sql:
            return [{"skill": "python", "label": "Python", "open_roles": 3, "active_candidates": 1}]
        if "from public.audit_events ae" in self.sql:
            return [{
                "id": "activity-1", "action": "candidate_created", "entity_type": "candidate",
                "entity_id": "candidate-1", "metadata": {}, "created_at": datetime(2026, 10, 13, 9, tzinfo=timezone.utc),
                "actor_user_id": USER, "actor_name": "Recruiter",
            }]
        raise AssertionError(f"Unexpected fetchall query: {self.sql}")


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class DashboardEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_scoped_metrics_pipeline_priorities_and_activity(self):
        cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection

        with patch.object(dashboard_router, "assert_org_member") as membership, patch.object(
            dashboard_router, "get_connection", fake_connection
        ):
            result = await dashboard_router.dashboard(
                organization_id=ORG, date_from=date(2026, 10, 1),
                date_to=date(2026, 10, 13), user_id=USER,
            )

        membership.assert_called_once_with(USER, ORG)
        self.assertEqual(result["metrics"]["open_jobs"], 2)
        self.assertEqual(result["metrics"]["active_candidates"], 8)
        self.assertEqual(result["metrics"]["interviews_today"], 1)
        self.assertEqual(result["metrics"]["placements_active"], 4)
        self.assertEqual(result["pipeline"]["new"], 2)
        self.assertEqual(result["pipeline"]["rejected"], 1)
        self.assertEqual(result["date_range"], {"from": "2026-10-01", "to": "2026-10-13"})
        self.assertTrue(any(item["type"] == "interview_today" and item["href"] == f"/interviews/{INTERVIEW}" for item in result["priorities"]))
        self.assertTrue(any(item["type"] == "offer_expiring" and item["href"] == f"/offers/{OFFER}" for item in result["priorities"]))
        self.assertTrue(any(item["type"] == "vacancy_health" and item["href"] == f"/jobs?job_id={JOB}" for item in result["priorities"]))
        self.assertEqual(result["activity"][0]["actor_name"], "Recruiter")
        self.assertEqual(result["team_workload"][0]["open_vacancies"], 2)
        self.assertEqual(result["talent_intelligence"][0]["gap"], 2)
        # Every data query must include the requested organisation scope.
        self.assertTrue(cursor.queries)
        for sql, params in cursor.queries:
            self.assertIn("organization_id", sql, f"Missing tenant scope in query: {sql}")
            self.assertIn(ORG, params, f"Missing requested organisation parameter: {sql}")

    async def test_rejects_non_member_before_database_access(self):
        with patch.object(
            dashboard_router, "assert_org_member", side_effect=HTTPException(status_code=403, detail="forbidden")
        ), patch.object(dashboard_router, "get_connection") as connection:
            with self.assertRaises(HTTPException) as error:
                await dashboard_router.dashboard(
                    organization_id=ORG, date_from=None, date_to=None, user_id=USER,
                )
        self.assertEqual(error.exception.status_code, 403)
        connection.assert_not_called()

    async def test_rejects_inverted_date_range_before_database_access(self):
        with patch.object(dashboard_router, "assert_org_member"), patch.object(
            dashboard_router, "get_connection"
        ) as connection:
            with self.assertRaises(HTTPException) as error:
                await dashboard_router.dashboard(
                    organization_id=ORG, date_from=date(2026, 10, 14),
                    date_to=date(2026, 10, 13), user_id=USER,
                )
        self.assertEqual(error.exception.status_code, 422)
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
