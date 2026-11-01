import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import saved_reports as reports

ORG = UUID("11111111-1111-4111-8111-111111111111")
OWNER = UUID("22222222-2222-4222-8222-222222222222")
OTHER = UUID("33333333-3333-4333-8333-333333333333")
REPORT = UUID("44444444-4444-4444-8444-444444444444")


def report_row(**overrides):
    row = {
        "id": REPORT,
        "organization_id": ORG,
        "created_by": OWNER,
        "name": "Monthly funnel",
        "description": None,
        "report_type": "funnel",
        "filters": {"date_from": "2026-10-01", "date_to": "2026-10-31"},
        "is_shared": False,
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.one = None
        self.many = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


class SavedReportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            with FakeConnection(self.cursor) as connection:
                yield connection

        self.connection_patch = patch.object(reports, "get_connection", fake_connection)
        self.member_patch = patch.object(reports, "assert_org_member")
        self.admin_patch = patch.object(reports, "assert_org_admin")
        self.role_patch = patch.object(reports, "get_org_role", return_value="recruiter")
        self.connection_patch.start()
        self.member = self.member_patch.start()
        self.admin = self.admin_patch.start()
        self.role = self.role_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.member_patch.stop)
        self.addCleanup(self.admin_patch.stop)
        self.addCleanup(self.role_patch.stop)

    async def test_list_returns_only_shared_and_owned_reports(self):
        self.cursor.many = [report_row()]
        result = await reports.list_saved_reports(ORG, OWNER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], str(REPORT))
        sql, params = self.cursor.queries[0]
        self.assertIn("is_shared=true or created_by=%s or %s=true", sql)
        self.assertEqual(params, [ORG, OWNER, False])
        self.member.assert_called_once_with(OWNER, ORG)

    async def test_admin_list_includes_private_reports_from_other_members(self):
        self.cursor.many = [report_row()]
        self.role.return_value = "admin"
        result = await reports.list_saved_reports(ORG, OTHER)
        self.assertEqual(len(result), 1)
        self.assertEqual(self.cursor.queries[0][1], [ORG, OTHER, True])

    async def test_non_member_is_rejected_before_database_query(self):
        self.member.side_effect = HTTPException(status_code=403, detail="Not a member")
        with self.assertRaises(HTTPException) as context:
            await reports.list_saved_reports(ORG, OTHER)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(self.cursor.queries, [])

    async def test_create_private_report_persists_tenant_and_owner(self):
        self.cursor.one = report_row()
        payload = reports.SavedReportCreate(
            name=" Monthly funnel ",
            report_type="funnel",
            filters={"date_from": "2026-10-01", "date_to": "2026-10-31"},
        )
        result = await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(result["name"], "Monthly funnel")
        self.assertFalse(result["is_shared"])
        sql, params = self.cursor.queries[0]
        self.assertIn("insert into public.saved_report_definitions", sql)
        self.assertEqual(params[0:2], [ORG, OWNER])
        self.assertEqual(params[2], "Monthly funnel")
        self.admin.assert_not_called()

    async def test_sharing_requires_organisation_admin(self):
        self.admin.side_effect = HTTPException(status_code=403, detail="Admin access required")
        payload = reports.SavedReportCreate(name="Shared funnel", report_type="funnel", is_shared=True)
        with self.assertRaises(HTTPException) as context:
            await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(self.cursor.queries, [])

    async def test_workload_rejects_unsupported_date_filter(self):
        payload = reports.SavedReportCreate(
            name="Workload",
            report_type="workload",
            filters={"date_from": "2026-10-01"},
        )
        with self.assertRaises(HTTPException) as context:
            await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(self.cursor.queries, [])

    async def test_forecast_rejects_job_filter(self):
        payload = reports.SavedReportCreate(
            name="Forecast",
            report_type="forecast",
            filters={"job_id": "55555555-5555-4555-8555-555555555555"},
        )
        with self.assertRaises(HTTPException) as context:
            await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 422)

    async def test_campaign_roi_report_type_uses_export_contract(self):
        self.cursor.one = report_row(report_type="campaign_roi")
        payload = reports.SavedReportCreate(name="Campaign", report_type="campaign_roi")
        result = await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(result["report_type"], "campaign_roi")

    async def test_null_required_patch_fields_are_rejected(self):
        payload = reports.SavedReportUpdate(report_type=None)
        with self.assertRaises(HTTPException) as context:
            await reports.update_saved_report(REPORT, ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(self.cursor.queries, [])

    async def test_admin_can_update_another_users_private_report(self):
        self.cursor.one = report_row()
        self.role.return_value = "admin"
        payload = reports.SavedReportUpdate(name="Admin edit")
        await reports.update_saved_report(REPORT, ORG, payload, OTHER)
        self.assertEqual(len(self.cursor.queries), 2)
        self.assertEqual(self.cursor.queries[0][1], [REPORT, ORG, OTHER, True])

    async def test_reversed_date_range_is_rejected(self):
        payload = reports.SavedReportCreate(
            name="Funnel",
            report_type="funnel",
            filters={"date_from": "2026-11-01", "date_to": "2026-10-01"},
        )
        with self.assertRaises(HTTPException) as context:
            await reports.create_saved_report(ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 422)

    async def test_get_hides_another_users_private_report(self):
        self.cursor.one = None
        with self.assertRaises(HTTPException) as context:
            await reports.get_saved_report(REPORT, ORG, OTHER)
        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("is_shared=true or created_by=%s or %s=true", self.cursor.queries[0][0])

    async def test_owner_can_update_private_report(self):
        self.cursor.one = report_row()
        payload = reports.SavedReportUpdate(name="Updated funnel")
        await reports.update_saved_report(REPORT, ORG, payload, OWNER)
        self.assertEqual(len(self.cursor.queries), 2)
        self.assertIn("update public.saved_report_definitions", self.cursor.queries[1][0])
        self.assertEqual(self.cursor.queries[1][1][0], "Updated funnel")
        self.admin.assert_not_called()

    async def test_only_admin_can_change_share_setting(self):
        self.cursor.one = report_row()
        self.admin.side_effect = HTTPException(status_code=403, detail="Admin access required")
        payload = reports.SavedReportUpdate(is_shared=True)
        with self.assertRaises(HTTPException) as context:
            await reports.update_saved_report(REPORT, ORG, payload, OWNER)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(len(self.cursor.queries), 1)

    async def test_other_member_cannot_edit_another_owners_private_report(self):
        self.cursor.one = None
        payload = reports.SavedReportUpdate(name="Intrusion")
        with self.assertRaises(HTTPException) as context:
            await reports.update_saved_report(REPORT, ORG, payload, OTHER)
        self.assertEqual(context.exception.status_code, 404)

    async def test_delete_private_report_requires_owner(self):
        self.cursor.one = report_row()
        self.role.return_value = "recruiter"
        with self.assertRaises(HTTPException) as context:
            await reports.delete_saved_report(REPORT, ORG, OTHER)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(len(self.cursor.queries), 1)


if __name__ == "__main__":
    unittest.main()
