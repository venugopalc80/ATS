import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.interviews import InterviewUpdate
from app.services.interview_service import InterviewService


class InterviewScheduleServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.interview_id = uuid4()
        self.organization_id = uuid4()
        self.actor_id = uuid4()
        self.new_time = datetime(2026, 11, 3, 10, 30, tzinfo=timezone.utc)

    def make_database(self, fetchone_results):
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        cursor.fetchone.side_effect = list(fetchone_results)
        return connection, cursor

    async def test_rescheduling_scheduled_interview_sets_rescheduled_status(self):
        existing = {"organization_id": self.organization_id, "status": "scheduled"}
        updated = {"id": self.interview_id, "status": "rescheduled", "scheduled_at": self.new_time}
        connection, cursor = self.make_database([existing, updated])
        payload = InterviewUpdate(scheduled_at=self.new_time)

        with patch("app.services.interview_service.get_connection", return_value=connection):
            result = await InterviewService().update_interview(self.interview_id, payload, self.actor_id)

        self.assertEqual(result, updated)
        update_call = next(
            call for call in cursor.execute.call_args_list
            if call.args[0].lower().startswith("update public.interviews")
        )
        self.assertIn("scheduled_at=%s", update_call.args[0])
        self.assertIn("status=%s", update_call.args[0])
        self.assertIn("rescheduled", update_call.args[1])

    async def test_terminal_interview_cannot_be_rescheduled_by_patching_date_only(self):
        existing = {"organization_id": self.organization_id, "status": "completed"}
        connection, cursor = self.make_database([existing])
        payload = InterviewUpdate(scheduled_at=self.new_time)

        with patch("app.services.interview_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "Only scheduled interviews can be rescheduled"):
                await InterviewService().update_interview(self.interview_id, payload, self.actor_id)

        self.assertFalse(any(
            call.args[0].lower().startswith("update public.interviews")
            for call in cursor.execute.call_args_list
        ))

    async def test_cancelled_interview_cannot_be_rescheduled(self):
        existing = {"organization_id": self.organization_id, "status": "cancelled"}
        connection, cursor = self.make_database([existing])
        payload = InterviewUpdate(scheduled_at=self.new_time, status="rescheduled")

        with patch("app.services.interview_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "Only scheduled interviews can be rescheduled"):
                await InterviewService().update_interview(self.interview_id, payload, self.actor_id)

        self.assertFalse(any(
            call.args[0].lower().startswith("update public.interviews")
            for call in cursor.execute.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
