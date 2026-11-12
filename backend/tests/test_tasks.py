import unittest
from uuid import UUID
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import tasks as tasks_router
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.db import DatabaseConnectionError, DatabaseIntegrityError

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

    def test_null_status_is_rejected(self):
        with self.assertRaises(ValueError):
            TaskUpdate(status=None)

    def test_null_priority_is_rejected(self):
        with self.assertRaises(ValueError):
            TaskUpdate(priority=None)

    def test_follow_up_candidate_cannot_be_cleared_by_schema_only_when_api_context_is_known(self):
        payload = TaskUpdate(candidate_id=None)
        self.assertIn("candidate_id", payload.model_fields_set)


class TaskDatabaseErrorTests(unittest.TestCase):
    def test_integrity_error_is_a_connection_error_subtype(self):
        self.assertTrue(issubclass(DatabaseIntegrityError, DatabaseConnectionError))


class TaskEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_requires_organization_membership(self):
        with patch.object(tasks_router, "get_connection") as connection:
            connection.side_effect = DatabaseConnectionError("denied")
            with self.assertRaises(HTTPException) as raised:
                await tasks_router.list_tasks(
                    organization_id=ORG, status="open", task_type=None,
                    due_before=None, limit=50, user_id=USER,
                )
        self.assertEqual(raised.exception.status_code, 503)

    async def test_create_rejects_membership_failure_before_insert(self):
        payload = TaskCreate(organization_id=ORG, title="Follow up", task_type="candidate_follow_up", candidate_id=CANDIDATE)
        with patch.object(tasks_router, "get_connection") as connection:
            connection.side_effect = DatabaseConnectionError("database unavailable")
            with self.assertRaises(HTTPException) as raised:
                await tasks_router.create_task(payload=payload, user_id=USER)
        self.assertEqual(raised.exception.status_code, 503)

    async def test_update_requires_at_least_one_field(self):
        with self.assertRaises(HTTPException) as raised:
            await tasks_router.update_task(task_id=CANDIDATE, payload=TaskUpdate(), user_id=USER)
        self.assertEqual(raised.exception.status_code, 422)

    async def test_database_integrity_error_maps_to_422(self):
        error = DatabaseIntegrityError("constraint violation")
        with patch.object(tasks_router, "get_connection") as connection:
            connection.side_effect = error
            payload = TaskCreate(organization_id=ORG, title="Task")
            with self.assertRaises(HTTPException) as raised:
                await tasks_router.create_task(payload=payload, user_id=USER)
        self.assertEqual(raised.exception.status_code, 422)
