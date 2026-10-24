import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from datetime import date
from uuid import UUID

from fastapi import HTTPException

from app.routers import analytics as analytics_router
from app.routers.analytics import _application_scope, _validate_dates


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
RECRUITER = UUID("44444444-4444-4444-8444-444444444444")


class AnalyticsFilterTests(unittest.TestCase):
    def test_csv_values_neutralize_spreadsheet_formula_prefixes(self):
        for value in ("=HYPERLINK(\\\"https://example.com\\\")", " +SUM(A1:A2)", "-2+3", "@cmd"):
            self.assertEqual(analytics_router._csv_safe_value(value), "'" + value)
        self.assertEqual(analytics_router._csv_safe_value("Referral"), "Referral")
        self.assertEqual(analytics_router._csv_safe_value(12.5), 12.5)
        self.assertIsNone(analytics_router._csv_safe_value(None))

    def test_application_scope_is_tenant_scoped_and_uses_half_open_dates(self):
        where, params = _application_scope(
            ORG, date(2026, 10, 1), date(2026, 10, 22), JOB, RECRUITER
        )
        self.assertIn("a.organization_id = %s", where)
        self.assertIn("a.created_at >= %s::date", where)
        self.assertIn("a.created_at < (%s::date + interval '1 day')", where)
        self.assertIn("a.job_id = %s", where)
        self.assertIn("j.recruiter_id = %s", where)
        self.assertEqual(params, [ORG, date(2026, 10, 1), date(2026, 10, 22), JOB, RECRUITER])

    def test_application_scope_without_optional_filters(self):
        where, params = _application_scope(ORG, None, None, None, None)
        self.assertEqual(where, "a.organization_id = %s")
        self.assertEqual(params, [ORG])

    def test_reversed_dates_are_rejected(self):
        with self.assertRaises(HTTPException) as context:
            _validate_dates(date(2026, 10, 22), date(2026, 10, 1))
        self.assertEqual(context.exception.status_code, 422)

    def test_missing_date_bounds_are_allowed(self):
        _validate_dates(None, None)
        _validate_dates(date(2026, 10, 1), None)
        _validate_dates(None, date(2026, 10, 22))


class FakeAnalyticsCursor:
    def __init__(self):
        self.sql = ""
        self.params = []
        self.queries = []
        self.fetchall_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params or []
        self.queries.append((self.sql, self.params))

    def fetchone(self):
        if "pending_headcount" in self.sql:
            return {"pending_headcount": 4, "pending_requisitions": 2}
        if "as applications" in self.sql:
            return {"applications": 6, "closed_unsuccessfully": 1, "active_applications": 4}
        if "as decided_offers" in self.sql:
            return {"decided_offers": 4, "accepted_offers": 3}
        if "as complete_requisitions" in self.sql:
            return {"median_days": 20.0, "complete_requisitions": 3}
        if "as open_more_than_30_days" in self.sql:
            return {
                "open_vacancies": 2,
                "open_more_than_30_days": 1,
                "missing_opened_at": 1,
                "median_days_open": 35.0,
            }
        if "as median_days" in self.sql:
            self.asserted_time_to_hire_query = self.sql
            return {"median_days": 12.5, "complete_records": 2}
        if "as cohort_size" in self.sql:
            return {"cohort_size": 6}
        if "as unassigned_open_vacancies" in self.sql:
            return {"unassigned_open_vacancies": 2, "unassigned_open_tasks": 3}
        raise AssertionError(f"Unexpected fetchone query: {self.sql}")

    def fetchall(self):
        if "approved_headcount" in self.sql and "months as" in self.sql:
            return [
                {"month_start": date(2026, 4, 1), "approved_headcount": 0, "approved_requisitions": 0},
                {"month_start": date(2026, 5, 1), "approved_headcount": 1, "approved_requisitions": 1},
                {"month_start": date(2026, 6, 1), "approved_headcount": 0, "approved_requisitions": 0},
                {"month_start": date(2026, 7, 1), "approved_headcount": 2, "approved_requisitions": 1},
                {"month_start": date(2026, 8, 1), "approved_headcount": 0, "approved_requisitions": 0},
                {"month_start": date(2026, 9, 1), "approved_headcount": 3, "approved_requisitions": 1},
            ]
        if "as stage_visits" in self.sql:
            return [
                {"stage": "screening", "stage_visits": 7, "distinct_applications": 6},
                {"stage": "interview", "stage_visits": 4, "distinct_applications": 3},
            ]
        if "as completed_intervals" in self.sql:
            return [{
                "stage": "screening", "completed_intervals": 4,
                "median_days": 2.0, "p75_days": 3.0, "p90_days": 5.0,
            }]
        if "as entered_applications" in self.sql:
            return [{
                "stage": "screening", "next_stage": "submitted",
                "entered_applications": 5, "reached_next_applications": 3,
                "conversion_rate": 0.6,
            }]
        if "group by a.status" in self.sql:
            return [{"status": "interview", "distinct_applications": 3}]
        if "as campaign_name" in self.sql and "spend_amount" in self.sql:
            return [{
                "campaign_id": UUID("55555555-5555-4555-8555-555555555555"),
                "campaign_name": "Engineering outreach",
                "campaign_status": "active",
                "budget_amount": 500,
                "budget_currency": "GBP",
                "channel_id": UUID("66666666-6666-4666-8666-666666666666"),
                "channel_key": "job_board",
                "source_label": "Job board",
                "spend_amount": 120,
                "spend_currency": "GBP",
                "applications": 10,
                "hires": 2,
                "applications_with_accepted_offer": 2,
            }]
        if "as source" in self.sql and "completed_interviews" in self.sql:
            return [{
                "source": "Referral",
                "applications": 10,
                "qualified_applications": 7,
                "completed_interviews": 5,
                "offers": 4,
                "decided_offers": 3,
                "accepted_offers": 2,
                "hires": 2,
            }, {
                "source": "Unknown",
                "applications": 2,
                "qualified_applications": 0,
                "completed_interviews": 0,
                "offers": 0,
                "decided_offers": 0,
                "accepted_offers": 0,
                "hires": 0,
            }]
        if "from member_scope ms" in self.sql:
            return [{
                "user_id": UUID("22222222-2222-4222-8222-222222222222"),
                "role": "recruiter",
                "name": "Example Recruiter",
                "open_vacancies": 2,
                "on_hold_vacancies": 1,
                "active_applications": 5,
                "upcoming_interviews": 3,
                "open_tasks": 4,
                "overdue_tasks": 1,
            }]
        raise AssertionError(f"Unexpected fetchall query: {self.sql}")


class FakeAnalyticsConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class AnalyticsEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cursor = FakeAnalyticsCursor()

        @contextmanager
        def fake_connection():
            with FakeAnalyticsConnection(self.cursor) as connection:
                yield connection

        self.connection_patch = patch.object(analytics_router, "get_connection", fake_connection)
        self.membership_patch = patch.object(analytics_router, "assert_org_member")
        self.connection_patch.start()
        self.membership = self.membership_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.membership_patch.stop)

    async def test_kpis_are_scoped_and_null_metrics_are_explicit(self):
        result = await analytics_router.analytics_kpis(
            organization_id=ORG,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 22),
            job_id=JOB,
            recruiter_id=RECRUITER,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        self.membership.assert_called_once()
        self.assertEqual(result["metrics"]["applications"]["value"], 6)
        self.assertEqual(result["metrics"]["offer_acceptance_rate"]["value"], 0.75)
        self.assertEqual(result["metrics"]["median_time_to_hire_days"]["value"], 12.5)
        self.assertEqual(result["metrics"]["median_time_to_fill_days"]["value"], 20.0)
        self.assertEqual(result["metrics"]["vacancy_ageing"]["median_days_open"], 35.0)
        self.assertEqual(result["metrics"]["vacancy_ageing"]["open_more_than_30_days"], 1)
        self.assertIn("organization_id = %s", self.cursor.queries[0][0])
        self.assertIn("j.recruiter_id = %s", self.cursor.queries[0][0])
        self.assertIn("select min(off.responded_at) as accepted_at", self.cursor.queries[2][0])

    async def test_kpis_reject_reversed_dates_before_querying(self):
        with self.assertRaises(HTTPException) as context:
            await analytics_router.analytics_kpis(
                organization_id=ORG,
                date_from=date(2026, 10, 22),
                date_to=date(2026, 10, 1),
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            )
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(self.cursor.queries, [])

    async def test_non_member_is_rejected_before_analytics_queries(self):
        self.membership.side_effect = HTTPException(status_code=403, detail="Not a member")
        with self.assertRaises(HTTPException) as context:
            await analytics_router.analytics_kpis(
                organization_id=ORG,
                date_from=None,
                date_to=None,
                job_id=None,
                recruiter_id=None,
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            )
        self.assertEqual(context.exception.status_code, 403)
        self.membership.assert_called_once()
        self.assertEqual(self.cursor.queries, [])

    async def test_funnel_reports_application_cohort_size_and_stage_visits(self):
        result = await analytics_router.analytics_funnel(
            organization_id=ORG,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 22),
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        self.assertEqual(result["sample_size"], 6)
        self.assertFalse(result["low_sample_size"])
        self.assertEqual(result["stages"][0]["stage_visits"], 7)
        self.assertEqual(result["stages"][0]["distinct_applications"], 6)
        self.assertEqual(result["stage_waiting_time"][0]["median_days"], 2.0)
        self.assertEqual(result["stage_waiting_time"][0]["p90_days"], 5.0)
        self.assertEqual(result["stage_conversions"][0]["conversion_rate"], 0.6)
        self.assertEqual(result["stage_conversions"][0]["entered_applications"], 5)
        self.assertIn("h.organization_id=%s", self.cursor.queries[0][0])
        self.assertIn("count(distinct h.application_id)", self.cursor.queries[3][0])
        self.assertIn("lead(h.created_at)", self.cursor.queries[1][0])


    async def test_workload_returns_counts_and_separates_unassigned_demand(self):
        result = await analytics_router.analytics_workload(
            organization_id=ORG,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        self.assertEqual(len(result["recruiters"]), 1)
        self.assertEqual(result["recruiters"][0]["open_vacancies"], 2)
        self.assertEqual(result["recruiters"][0]["overdue_tasks"], 1)
        self.assertEqual(result["unassigned"]["unassigned_open_vacancies"], 2)
        self.assertEqual(result["unassigned"]["unassigned_open_tasks"], 3)
        self.assertIsNone(result["definitions"]["capacity_score"])
        self.assertIn("organization_id=%s", self.cursor.queries[0][0])
        self.membership.assert_called_once()


    async def test_source_metrics_use_decided_offer_denominator_and_flag_small_samples(self):
        result = await analytics_router.analytics_sources(
            organization_id=ORG,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 22),
            job_id=None,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        self.assertEqual(result["sources"][0]["offer_acceptance_rate"], 2 / 3)
        self.assertFalse(result["sources"][0]["sample_warning"])
        self.assertTrue(result["sources"][1]["sample_warning"])
        self.assertIsNone(result["sources"][1]["offer_acceptance_rate"])
        self.assertIn("coalesce(nullif(btrim(a.source), ''), 'Unknown')", self.cursor.queries[0][0])


    async def test_forecast_uses_six_month_baseline_and_exposes_pending_demand(self):
        result = await analytics_router.analytics_forecast(
            organization_id=ORG,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        forecast = result["forecast"]
        self.assertEqual(result["history_months"], 6)
        self.assertEqual(forecast["expected_approved_headcount"], 1.0)
        self.assertEqual(forecast["pending_approval_headcount"], 4)
        self.assertEqual(forecast["pending_approval_requisitions"], 2)
        self.assertEqual(forecast["trend"], "increasing")
        self.assertEqual(forecast["confidence"], "medium")
        self.assertEqual(forecast["status"], "baseline_only")
        self.assertIn("generate_series", self.cursor.queries[0][0])
        self.membership.assert_called_once()


    async def test_export_endpoint_returns_csv_for_allowlisted_forecast_report(self):
        response = await analytics_router.analytics_export(
            organization_id=ORG,
            report_type="forecast",
            date_from=None,
            date_to=None,
            job_id=None,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        self.assertTrue(response.media_type.startswith("text/csv"))
        self.assertIn("aqerith-forecast-report.csv", response.headers["content-disposition"])
        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks).decode()
        self.assertIn("record_type", body)
        self.assertIn("approved_headcount", body)
        self.assertIn("expected_approved_headcount", body)


    async def test_export_endpoint_sanitizes_untrusted_source_labels(self):
        payload = {
            "sources": [{
                "source": "=HYPERLINK(\"https://example.com\")",
                "applications": 1,
                "qualified_applications": 0,
                "completed_interviews": 0,
                "offers": 0,
                "decided_offers": 0,
                "accepted_offers": 0,
                "hires": 0,
                "offer_acceptance_rate": None,
                "conversion_rate": None,
                "sample_warning": True,
            }]
        }
        with patch.object(analytics_router, "analytics_sources", new=AsyncMock(return_value=payload)):
            response = await analytics_router.analytics_export(
                organization_id=ORG,
                report_type="sources",
                date_from=None,
                date_to=None,
                job_id=None,
                recruiter_id=None,
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            )
        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks).decode()
        self.assertIn("'=HYPERLINK", body)
        self.assertNotIn('"=HYPERLINK', body)

    async def test_campaign_efficiency_reports_costs_without_inventing_financial_roi(self):
        result = await analytics_router.analytics_campaign_roi(
            organization_id=ORG,
            date_from=None,
            date_to=None,
            job_id=None,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        row = result["campaign_channels"][0]
        self.assertEqual(row["cost_per_application"], 12.0)
        self.assertEqual(row["cost_per_hire"], 60.0)
        self.assertIsNone(row["financial_roi"])
        self.assertEqual(row["financial_roi_status"], "revenue_data_not_available")
        self.assertEqual(row["cost_metrics_status"], "all_time_channel_spend_snapshot")
        self.assertFalse(row["sample_warning"])
        self.assertIn("campaign_memberships", self.cursor.queries[0][0])


    async def test_campaign_period_filters_do_not_misstate_lifetime_spend_as_period_cost(self):
        result = await analytics_router.analytics_campaign_roi(
            organization_id=ORG,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 22),
            job_id=None,
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        row = result["campaign_channels"][0]
        self.assertIsNone(row["cost_per_application"])
        self.assertIsNone(row["cost_per_hire"])
        self.assertEqual(row["cost_metrics_status"], "period_spend_history_not_available")


    async def test_campaign_cost_ratios_are_unavailable_for_job_or_recruiter_slices(self):
        result = await analytics_router.analytics_campaign_roi(
            organization_id=ORG,
            date_from=None,
            date_to=None,
            job_id=UUID("33333333-3333-4333-8333-333333333333"),
            recruiter_id=None,
            user_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        row = result["campaign_channels"][0]
        self.assertIsNone(row["cost_per_application"])
        self.assertIsNone(row["cost_per_hire"])
        self.assertEqual(row["cost_metrics_status"], "spend_not_segmented_for_filters")


if __name__ == "__main__":
    unittest.main()
