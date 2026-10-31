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
        self.job_status = "open"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if "select timezone from public.organizations" in self.sql:
            return {"timezone": "Europe/London"}
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
                "status": self.job_status, "applicants": 1, "days_open": 42,
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
        self.assertEqual(result["timezone"], "Europe/London")
        count_query = next((sql, params) for sql, params in cursor.queries if "from public.interviews where" in sql)
        self.assertIn("scheduled_at >= %s and scheduled_at < %s", count_query[0])
        self.assertEqual(count_query[1][0], ORG)
        self.assertEqual(len(count_query[1]), 3)
        list_query = next((sql, params) for sql, params in cursor.queries if "from public.interviews i" in sql and "feedback is null" not in sql)
        self.assertIn("scheduled_at >= %s", list_query[0])
        self.assertEqual(list_query[1][0], ORG)
        self.assertEqual(len(list_query[1]), 3)
        self.assertEqual(result["metrics"]["placements_active"], 4)
        self.assertEqual(result["pipeline"]["new"], 2)
        self.assertEqual(result["pipeline"]["rejected"], 1)
        self.assertEqual(result["date_range"], {"from": "2026-10-01", "to": "2026-10-13"})
        self.assertTrue(any(item["type"] == "interview_today" and item["href"] == f"/interviews?interview_id={INTERVIEW}" for item in result["priorities"]))
        self.assertTrue(any(item["type"] == "offer_expiring" and item["href"] == f"/offers?offer_id={OFFER}" for item in result["priorities"]))
        self.assertTrue(any(item["type"] == "vacancy_health" and item["href"] == f"/jobs?job_id={JOB}" for item in result["priorities"]))
        self.assertEqual(result["activity"][0]["actor_name"], "Recruiter")
        # Every data query must include the requested organisation scope.
        self.assertTrue(cursor.queries)
        for sql, params in cursor.queries:
            if "select timezone from public.organizations" in sql:
                self.assertIn("where id=%s", sql)
            else:
                self.assertIn("organization_id", sql, f"Missing tenant scope in query: {sql}")
            self.assertIn(ORG, params, f"Missing requested organisation parameter: {sql}")


    def test_organisation_day_bounds_handle_timezone_and_dst(self):
        helper = dashboard_router.organisation_day_bounds_utc
        start, end = helper("Europe/London", datetime(2026, 7, 15, 12, tzinfo=timezone.utc))
        self.assertEqual(start, datetime(2026, 7, 14, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 7, 15, 23, tzinfo=timezone.utc))
        start, end = helper("Asia/Kolkata", datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
        self.assertEqual(start, datetime(2026, 10, 12, 18, 30, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 10, 13, 18, 30, tzinfo=timezone.utc))
        start, end = helper("Europe/London", datetime(2026, 3, 29, 12, tzinfo=timezone.utc))
        self.assertEqual((end - start).total_seconds(), 23 * 3600)
        start, end = helper("Europe/London", datetime(2026, 10, 25, 12, tzinfo=timezone.utc))
        self.assertEqual((end - start).total_seconds(), 25 * 3600)

    def test_invalid_organisation_timezone_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            dashboard_router.organisation_day_bounds_utc("Not/A_Real_Zone")
        self.assertEqual(error.exception.status_code, 500)

    async def test_on_hold_vacancy_is_flagged_for_attention(self):
        cursor = FakeCursor()
        cursor.job_status = "on_hold"

        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection

        with patch.object(dashboard_router, "assert_org_member"), patch.object(
            dashboard_router, "get_connection", fake_connection
        ):
            result = await dashboard_router.dashboard(
                organization_id=ORG, date_from=None, date_to=None, user_id=USER,
            )

        self.assertEqual(result["jobs"][0]["health"], "needs_attention")
        self.assertIn("Role is on hold", result["jobs"][0]["health_reasons"])
        vacancy_query = next(sql for sql, _params in cursor.queries if "left join public.applications" in sql)
        self.assertIn("order by case when j.status='on_hold' then 0 else 1 end", vacancy_query)
        self.assertIn("coalesce(j.opened_at,j.created_at) asc limit 10", vacancy_query)

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
