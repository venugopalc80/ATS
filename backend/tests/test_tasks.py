import unittest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import tasks as tasks_router
from app.schemas.tasks import TaskCreate, TaskUpdate

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
CANDIDATE = UUID("33333333-3333-4333-8333-333333333333")


class TaskSchemaTests(unittest.TestCase):
    def test_follow_up_requires_candidate(self):
        with self.assertRaises(ValueError):
            TaskCreate(organization_id=ORG, title="Call candidate", task_type="candidate_follow_up")

    def test_title_is_trimmed_and_valid_priority_is_kept(self):
        task = TaskCreate(organization_id=ORG, title="  Review shortlist  ", priority="high")
        self.assertEqual(task.title, "Review shortlist")
        self.assertEqual(task.priority, "high")

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            TaskUpdate(status="deleted")


class TaskEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_requires_organization_membership(self):
        with patch.object(tasks_router, "assert_org_member", side_effect=HTTPException(403, "forbidden")):
            with self.assertRaises(HTTPException) as raised:
                await tasks_router.list_tasks(
                    organization_id=ORG, status="open", task_type=None,
                    due_before=None, limit=50, user_id=USER,
                )
        self.assertEqual(raised.exception.status_code, 403)

    async def test_create_checks_org_membership_before_database(self):
        payload = TaskCreate(organization_id=ORG, title="Follow up", task_type="candidate_follow_up", candidate_id=CANDIDATE)
        with patch.object(tasks_router, "assert_org_member", side_effect=HTTPException(403, "forbidden")), patch.object(
            tasks_router, "_ensure_links"
        ) as ensure_links:
            with self.assertRaises(HTTPException) as raised:
                await tasks_router.create_task(payload=payload, user_id=USER)
        self.assertEqual(raised.exception.status_code, 403)
        ensure_links.assert_not_called()
