import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import tasks as tasks_router


ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("99999999-9999-4999-8999-999999999999")
USER = UUID("22222222-2222-4222-8222-222222222222")


class RecruiterTaskSchemaTests(unittest.TestCase):
    def test_rejects_blank_title(self):
        with self.assertRaises(ValidationError):
            tasks_router.TaskCreate(organization_id=ORG, title="   ")

    def test_rejects_unknown_task_type(self):
        with self.assertRaises(ValidationError):
            tasks_router.TaskCreate(organization_id=ORG, title="Follow up", task_type="something_else")

    def test_accepts_candidate_follow_up(self):
        task = tasks_router.TaskCreate(
            organization_id=ORG, title="  Call candidate  ", task_type="candidate_follow_up", priority="high"
        )
        self.assertEqual(task.title, "Call candidate")
        self.assertEqual(task.task_type, "candidate_follow_up")
        self.assertEqual(task.priority, "high")


class RecruiterTaskAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_member_cannot_create_task_or_read_database(self):
        payload = tasks_router.TaskCreate(organization_id=OTHER_ORG, title="Follow up")
        with patch.object(
            tasks_router, "assert_org_member",
            side_effect=HTTPException(status_code=403, detail="not a member"),
        ), patch.object(tasks_router, "get_connection") as connection:
            with self.assertRaises(HTTPException) as error:
                await tasks_router.create_task(payload, user_id=USER)
        self.assertEqual(error.exception.status_code, 403)
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
