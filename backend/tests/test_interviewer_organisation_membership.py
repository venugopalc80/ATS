import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.interviews import InterviewCreate, InterviewUpdate
from app.services.interview_service import InterviewService


class InterviewerOrganisationMembershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.organization_id = uuid4()
        self.application_id = uuid4()
        self.interviewer_id = uuid4()
        self.actor_id = uuid4()
        self.interview_id = uuid4()

    def make_database(self, fetchone_results=(), fetchall_results=()):
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        cursor.fetchone.side_effect = list(fetchone_results)
        cursor.fetchall.return_value = list(fetchall_results)
        return connection, cursor

    def create_payload(self, interviewer_ids):
        return InterviewCreate(
            organization_id=self.organization_id,
            application_id=self.application_id,
            scheduled_at=datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc),
            interviewer_ids=interviewer_ids,
        )

    async def test_create_rejects_interviewer_from_another_organisation(self):
        connection, cursor = self.make_database(fetchone_results=[{"application_id": self.application_id}])
        payload = self.create_payload([self.interviewer_id])

        with patch("app.services.interview_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "interviewers must belong"):
                await InterviewService().create_interview(payload, self.actor_id)

        self.assertEqual(cursor.execute.call_count, 2)
        self.assertFalse(any("insert into public.interviews" in call.args[0].lower() for call in cursor.execute.call_args_list))

    async def test_create_accepts_interviewer_who_is_an_organisation_member(self):
        connection, cursor = self.make_database(
            fetchone_results=[{"application_id": self.application_id}, {"id": self.interview_id}],
            fetchall_results=[{"user_id": self.interviewer_id}],
        )
        payload = self.create_payload([self.interviewer_id])

        with patch("app.services.interview_service.get_connection", return_value=connection):
            result = await InterviewService().create_interview(payload, self.actor_id)

        self.assertEqual(result, {"id": self.interview_id})
        self.assertTrue(any("insert into public.interviews" in call.args[0].lower() for call in cursor.execute.call_args_list))

    async def test_update_rejects_interviewer_from_another_organisation(self):
        connection, cursor = self.make_database(
            fetchone_results=[{"organization_id": self.organization_id, "status": "scheduled"}],
        )
        payload = InterviewUpdate(interviewer_ids=[self.interviewer_id])

        with patch("app.services.interview_service.get_connection", return_value=connection):
            with self.assertRaisesRegex(ValueError, "interviewers must belong"):
                await InterviewService().update_interview(self.interview_id, payload, self.actor_id)

        self.assertEqual(cursor.execute.call_count, 2)
        self.assertFalse(any("update public.interviews" in call.args[0].lower() for call in cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
