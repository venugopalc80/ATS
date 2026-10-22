import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from app.routers import jobs as jobs_router
from app.routers import requisitions as requisitions_router
from app.schemas.jobs import JobUpdate

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
JOB = UUID("33333333-3333-4333-8333-333333333333")


def fake_connection(cursor):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    context_cursor = MagicMock()
    context_cursor.__enter__.return_value = cursor
    context_cursor.__exit__.return_value = False
    connection.cursor.return_value = context_cursor
    return connection


class JobStatusTransitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_job_cannot_transition_back_to_draft(self):
        existing = {"id": JOB, "organization_id": ORG, "status": "open"}
        with patch.object(jobs_router.service, "get_job", return_value=existing), \
             patch.object(jobs_router, "assert_org_member"), \
             patch.object(jobs_router, "get_org_role", return_value="recruiter"):
            with self.assertRaises(HTTPException) as raised:
                await jobs_router.update_job(JOB, JobUpdate(status="draft"), BackgroundTasks(), USER)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_viewer_cannot_be_assigned_as_job_recruiter(self):
        existing = {"id": JOB, "organization_id": ORG, "status": "draft"}
        cursor = MagicMock()
        cursor.fetchone.return_value = {"role": "viewer"}
        with patch.object(jobs_router.service, "get_job", return_value=existing), \
             patch.object(jobs_router, "assert_org_member"), \
             patch.object(jobs_router, "get_org_role", return_value="admin"), \
             patch.object(jobs_router, "get_connection", return_value=fake_connection(cursor)):
            with self.assertRaises(HTTPException) as raised:
                await jobs_router.update_job(JOB, JobUpdate(recruiter_id=USER), BackgroundTasks(), USER)
        self.assertEqual(raised.exception.status_code, 422)

    async def test_non_member_cannot_be_assigned_as_job_hiring_manager(self):
        existing = {"id": JOB, "organization_id": ORG, "status": "draft"}
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with patch.object(jobs_router.service, "get_job", return_value=existing), \
             patch.object(jobs_router, "assert_org_member"), \
             patch.object(jobs_router, "get_org_role", return_value="admin"), \
             patch.object(jobs_router, "get_connection", return_value=fake_connection(cursor)):
            with self.assertRaises(HTTPException) as raised:
                await jobs_router.update_job(JOB, JobUpdate(hiring_manager_id=USER), BackgroundTasks(), USER)
        self.assertEqual(raised.exception.status_code, 422)


class RequisitionRouteOrderTests(unittest.TestCase):
    def test_static_assignee_route_precedes_dynamic_id_route(self):
        paths = [route.path for route in requisitions_router.router.routes]
        self.assertLess(paths.index("/assignees"), paths.index("/{requisition_id}"))
