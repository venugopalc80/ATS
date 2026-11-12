import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.applications import ApplicationUpdate
from app.services.application_service import ApplicationService


class ApplicationLifecycleLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_read_locks_row_before_validating_transition(self):
        application_id = uuid4()
        actor_id = uuid4()
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {"status": "new"},
            {"id": application_id, "status": "screening"},
        ]

        with patch("app.services.application_service.get_connection", return_value=connection):
            result = await ApplicationService().update_application(
                application_id,
                ApplicationUpdate(status="screening"),
                actor_id,
            )

        status_read = cursor.execute.call_args_list[0].args[0].lower()
        self.assertIn("for update", status_read)
        self.assertEqual(result["status"], "screening")


if __name__ == "__main__":
    unittest.main()
