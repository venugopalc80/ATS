import unittest
from datetime import date
from uuid import UUID

from fastapi import HTTPException

from app.routers.analytics import _application_scope, _validate_dates


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
RECRUITER = UUID("44444444-4444-4444-8444-444444444444")


class AnalyticsFilterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
