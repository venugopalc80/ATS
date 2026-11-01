import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers import candidates, applications


class CandidatePermissionRouteTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.candidate_id = uuid4()
        self.row = {
            "id": self.candidate_id,
            "organization_id": self.organization_id,
            "first_name": "Alex",
            "last_name": "Taylor",
            "email": "alex@example.com",
            "phone": "+44123456789",
            "city": "London",
            "region": None,
            "country_code": "GB",
            "status": "active",
            "current_title": "Engineer",
            "years_experience": None,
            "skills": [],
            "resume_path": None,
            "resume_text": None,
            "ai_summary": None,
            "consent_recorded_at": None,
            "consent_purpose": None,
            "retention_until": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def test_candidate_list_redacts_contact_without_contact_permission(self):
        with patch.object(candidates, "require_permission") as permission, patch.object(
            candidates.service, "list_candidates", new=AsyncMock(return_value=[self.row])
        ) as list_rows:
            permission.side_effect = [None, HTTPException(403, "denied")]
            result = asyncio.run(candidates.list_candidates(self.organization_id, None, None, self.user_id))
        self.assertIsNone(result[0].email)
        self.assertIsNone(result[0].phone)
        list_rows.assert_awaited_once_with(
            self.organization_id, None, None, include_contact_search=False
        )

    def test_candidate_list_requires_basic_permission(self):
        denied = HTTPException(403, "denied")
        with patch.object(candidates, "require_permission", side_effect=denied), patch.object(
            candidates.service, "list_candidates", new=AsyncMock()
        ) as list_rows:
            with self.assertRaises(HTTPException):
                asyncio.run(candidates.list_candidates(self.organization_id, None, None, self.user_id))
        list_rows.assert_not_awaited()

    def test_candidate_detail_checks_permission_before_loading_full_record(self):
        calls = []
        async def get_org(_candidate_id):
            calls.append("org")
            return self.organization_id
        async def get_candidate(_candidate_id):
            calls.append("full")
            return self.row
        def permission(_user_id, _org_id, key):
            calls.append(key)
            if key == "candidate.read_contact":
                raise HTTPException(403, "denied")
        with patch.object(candidates.service, "get_candidate_organization_id", new=AsyncMock(side_effect=get_org)), patch.object(
            candidates.service, "get_candidate", new=AsyncMock(side_effect=get_candidate)
        ), patch.object(candidates, "require_permission", side_effect=permission):
            result = asyncio.run(candidates.get_candidate(self.candidate_id, self.user_id))
        self.assertEqual(calls, ["org", "candidate.read_basic", "candidate.read_contact", "full"])
        self.assertIsNone(result.email)
        self.assertIsNone(result.phone)


class ApplicationPermissionRouteTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.application_id = uuid4()
        self.row = {
            "id": self.application_id,
            "organization_id": self.organization_id,
            "job_id": uuid4(),
            "candidate_id": uuid4(),
            "source": "direct",
            "status": "new",
            "match_score": None,
            "match_explanation": None,
            "human_reviewed": False,
            "human_reviewed_by": None,
            "human_reviewed_at": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def test_application_list_requires_read_permission(self):
        denied = HTTPException(403, "denied")
        with patch.object(applications, "require_permission", side_effect=denied), patch.object(
            applications.service, "list_applications", new=AsyncMock()
        ) as list_rows:
            with self.assertRaises(HTTPException):
                asyncio.run(applications.list_applications(self.organization_id, None, None, None, self.user_id))
        list_rows.assert_not_awaited()

    def test_application_detail_checks_permission_before_loading_record(self):
        calls = []
        async def get_org(_application_id):
            calls.append("org")
            return self.organization_id
        async def get_application(_application_id):
            calls.append("full")
            return self.row
        def permission(_user_id, _org_id, key):
            calls.append(key)
        with patch.object(applications.service, "get_application_organization_id", new=AsyncMock(side_effect=get_org)), patch.object(
            applications.service, "get_application", new=AsyncMock(side_effect=get_application)
        ), patch.object(applications, "require_permission", side_effect=permission):
            result = asyncio.run(applications.get_application(self.application_id, self.user_id))
        self.assertEqual(calls, ["org", "application.read", "full"])
        self.assertEqual(result.id, self.application_id)


if __name__ == "__main__":
    unittest.main()
