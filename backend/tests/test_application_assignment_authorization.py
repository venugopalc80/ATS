import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers.application_assignments import (
    get_application_assignment,
    set_application_assignment,
)
from app.schemas.application_assignments import ApplicationAssignmentUpdate

APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
RECRUITER = UUID("33333333-3333-4333-8333-333333333333")


class ApplicationAssignmentAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.application_assignments.service.assign", new_callable=AsyncMock)
    @patch("app.routers.application_assignments._get_application_for_member", return_value=None)
    async def test_cross_tenant_application_is_hidden(self, lookup, assign):
        with self.assertRaises(HTTPException) as raised:
            await set_application_assignment(
                APPLICATION,
                ApplicationAssignmentUpdate(recruiter_id=RECRUITER, reason="Workload balancing"),
                user_id=USER,
            )
        self.assertEqual(raised.exception.status_code, 404)
        assign.assert_not_awaited()

    @patch("app.routers.application_assignments.service.assign", new_callable=AsyncMock)
    @patch("app.routers.application_assignments.assert_org_admin",
           side_effect=HTTPException(status_code=403, detail="Admin access required"))
    @patch("app.routers.application_assignments._get_application_for_member",
           return_value={"organization_id": ORG})
    async def test_non_admin_cannot_assign_recruiter(self, lookup, assert_admin, assign):
        with self.assertRaises(HTTPException) as raised:
            await set_application_assignment(
                APPLICATION,
                ApplicationAssignmentUpdate(recruiter_id=RECRUITER, reason="Workload balancing"),
                user_id=USER,
            )
        self.assertEqual(raised.exception.status_code, 403)
        assign.assert_not_awaited()

    @patch("app.routers.application_assignments.service.get", new_callable=AsyncMock)
    @patch("app.routers.application_assignments.assert_org_member",
           side_effect=HTTPException(status_code=403, detail="Not an organisation member"))
    @patch("app.routers.application_assignments._get_application_for_member",
           return_value={"organization_id": ORG})
    async def test_non_member_cannot_read_assignment(self, lookup, assert_member, get_assignment):
        with self.assertRaises(HTTPException) as raised:
            await get_application_assignment(APPLICATION, user_id=USER)
        self.assertEqual(raised.exception.status_code, 403)
        get_assignment.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
