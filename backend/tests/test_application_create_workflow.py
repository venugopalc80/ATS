import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.applications import ApplicationCreate
from app.services.application_service import ApplicationService


class ApplicationCreateWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.organization_id = uuid4()
        self.job_id = uuid4()
        self.candidate_id = uuid4()
        self.payload = ApplicationCreate(
            organization_id=self.organization_id,
            job_id=self.job_id,
            candidate_id=self.candidate_id,
            source="recruiter",
        )

    def make_database(self, fetch_results):
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        cursor.fetchone.side_effect = fetch_results
        return connection, cursor

    async def test_new_application_cannot_be_created_in_a_later_stage(self):
        with self.assertRaises(ValidationError):
            ApplicationCreate(
                organization_id=self.organization_id,
                job_id=self.job_id,
                candidate_id=self.candidate_id,
                status="hired",
            )

    async def test_closed_job_is_rejected_before_insert(self):
        connection, cursor = self.make_database([{"job_status": "closed", "candidate_ok": True}])
        with patch("app.services.application_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "open jobs"):
                await ApplicationService().create_application(self.payload)
        self.assertEqual(cursor.execute.call_count, 1)

    async def test_missing_or_wrong_tenant_job_is_rejected_before_insert(self):
        connection, cursor = self.make_database([{"job_status": None, "candidate_ok": True}])
        with patch("app.services.application_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "open jobs"):
                await ApplicationService().create_application(self.payload)
        self.assertEqual(cursor.execute.call_count, 1)

    async def test_wrong_tenant_candidate_is_rejected_before_insert(self):
        connection, cursor = self.make_database([{"job_status": "open", "candidate_ok": False}])
        with patch("app.services.application_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "same organization"):
                await ApplicationService().create_application(self.payload)
        self.assertEqual(cursor.execute.call_count, 1)

    async def test_duplicate_candidate_job_application_is_rejected_before_insert(self):
        connection, cursor = self.make_database([
            {"job_status": "open", "candidate_ok": True},
            {"duplicate_application": True},
        ])
        with patch("app.services.application_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "already has an application"):
                await ApplicationService().create_application(self.payload)
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertIn("pg_advisory_xact_lock", cursor.execute.call_args_list[1].args[0])

    async def test_open_job_creates_application_at_new_stage(self):
        application_id = uuid4()
        created = {"id": application_id, "status": "new"}
        connection, cursor = self.make_database([
            {"job_status": "open", "candidate_ok": True},
            {"duplicate_application": False},
            created,
        ])
        with patch("app.services.application_service.get_connection", return_value=connection):
            result = await ApplicationService().create_application(self.payload)
        self.assertEqual(result, created)
        self.assertEqual(cursor.execute.call_count, 4)
        self.assertIn("pg_advisory_xact_lock", cursor.execute.call_args_list[1].args[0])
        insert_sql, insert_params = cursor.execute.call_args.args
        self.assertIn("values (%s, %s, %s, %s, 'new')", insert_sql)
        self.assertEqual(insert_params, [self.organization_id, self.job_id, self.candidate_id, "recruiter"])

    async def test_duplicate_insert_race_returns_duplicate_error(self):
        connection, cursor = self.make_database([
            {"job_status": "open", "candidate_ok": True},
            {"duplicate_application": False},
            None,
        ])
        with patch("app.services.application_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "already has an application"):
                await ApplicationService().create_application(self.payload)
        insert_sql = cursor.execute.call_args_list[-1].args[0].lower()
        self.assertIn("on conflict (job_id, candidate_id) do nothing", insert_sql)


if __name__ == "__main__":
    unittest.main()
