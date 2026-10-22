import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.interviews import InterviewUpdate
from app.services.interview_service import InterviewService


class InterviewLifecycleLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_read_locks_row_before_validating_transition(self):
        interview_id = uuid4()
        organization_id = uuid4()
        actor_id = uuid4()
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {"organization_id": organization_id, "status": "scheduled"},
            {"id": interview_id, "status": "completed"},
        ]

        with patch("app.services.interview_service.get_connection", return_value=connection):
            result = await InterviewService().update_interview(
                interview_id,
                InterviewUpdate(status="completed"),
                actor_id,
            )

        status_read = cursor.execute.call_args_list[0].args[0].lower()
        self.assertIn("for update", status_read)
        self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
