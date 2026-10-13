import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers import candidate_tags as router
from app.schemas.candidate_tags import CandidateTagCreate


class CandidateTagRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.candidate_id = uuid4()
        self.tag_id = uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.tag_row = {
            "id": self.tag_id,
            "organization_id": self.organization_id,
            "name": "Shortlist",
            "colour": "#64748b",
            "created_by": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.created_at,
        }

    async def test_list_assignments_requires_org_membership(self):
        with patch.object(router, "assert_org_member", side_effect=HTTPException(403)), patch.object(
            router.service, "list_candidate_assignments", new_callable=AsyncMock
        ) as list_assignments:
            with self.assertRaises(HTTPException) as raised:
                await router.list_candidate_assignments(self.organization_id, self.user_id)
        self.assertEqual(raised.exception.status_code, 403)
        list_assignments.assert_not_awaited()

    async def test_create_tag_requires_admin(self):
        payload = CandidateTagCreate(organization_id=self.organization_id, name="Shortlist")
        with patch.object(router, "assert_org_admin", side_effect=HTTPException(403)), patch.object(
            router.service, "create_tag", new_callable=AsyncMock
        ) as create_tag:
            with self.assertRaises(HTTPException) as raised:
                await router.create_tag(payload, self.user_id)
        self.assertEqual(raised.exception.status_code, 403)
        create_tag.assert_not_awaited()

    async def test_create_tag_passes_org_and_actor_to_service(self):
        payload = CandidateTagCreate(organization_id=self.organization_id, name="Shortlist")
        with patch.object(router, "assert_org_admin") as require_admin, patch.object(
            router.service, "create_tag", new_callable=AsyncMock, return_value=self.tag_row
        ) as create_tag:
            result = await router.create_tag(payload, self.user_id)
        require_admin.assert_called_once_with(self.user_id, self.organization_id)
        create_tag.assert_awaited_once_with(payload, self.user_id)
        self.assertEqual(result.id, self.tag_id)
        self.assertEqual(result.organization_id, self.organization_id)

    async def test_candidate_specific_list_hides_cross_org_candidate(self):
        other_org = uuid4()
        candidate = {"id": self.candidate_id, "organization_id": other_org}
        with patch.object(router, "assert_org_member"), patch(
            "app.services.candidate_service.CandidateService.get_candidate",
            new_callable=AsyncMock,
            return_value=candidate,
        ), patch.object(router.service, "list_tags", new_callable=AsyncMock) as list_tags:
            with self.assertRaises(HTTPException) as raised:
                await router.list_tags(self.organization_id, self.candidate_id, self.user_id)
        self.assertEqual(raised.exception.status_code, 404)
        list_tags.assert_not_awaited()

    async def test_assign_rejects_cross_org_candidate_or_tag(self):
        with patch.object(router, "assert_org_member"), patch.object(
            router.service, "assign_tag", new_callable=AsyncMock,
            side_effect=ValueError("Candidate and tag must belong to the selected organisation"),
        ) as assign_tag:
            with self.assertRaises(HTTPException) as raised:
                await router.assign_tag(
                    self.tag_id, self.candidate_id, self.organization_id, self.user_id
                )
        self.assertEqual(raised.exception.status_code, 404)
        assign_tag.assert_awaited_once_with(
            self.organization_id, self.candidate_id, self.tag_id, self.user_id
        )

    async def test_database_connection_failure_returns_503(self):
        with patch.object(router, "assert_org_member"), patch.object(
            router.service, "list_candidate_assignments", new_callable=AsyncMock,
            side_effect=router.DatabaseConnectionError("test"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await router.list_candidate_assignments(self.organization_id, self.user_id)
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
