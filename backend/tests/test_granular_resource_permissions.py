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



class OfferCompensationPermissionTests(unittest.TestCase):
    def test_salary_write_requires_offer_management_and_salary_management(self):
        from types import SimpleNamespace
        from app.routers.offers import _require_offer_write

        payload = SimpleNamespace(model_fields_set={"salary_amount"})
        with patch("app.routers.offers.require_permission") as permission:
            _require_offer_write(uuid4(), uuid4(), payload)
        self.assertEqual(
            [call.args[2] for call in permission.call_args_list],
            ["offer.manage", "offer.salary.manage"],
        )

    def test_non_salary_offer_update_requires_offer_management_only(self):
        from types import SimpleNamespace
        from app.routers.offers import _require_offer_write

        payload = SimpleNamespace(model_fields_set={"status"})
        with patch("app.routers.offers.require_permission") as permission:
            _require_offer_write(uuid4(), uuid4(), payload)
        permission.assert_called_once()
        self.assertEqual(permission.call_args.args[2], "offer.manage")

    def test_salary_output_is_redacted_without_salary_read_permission(self):
        from app.routers.offers import _offer_output

        row = {
            "organization_id": uuid4(),
            "application_id": uuid4(),
            "title": "Engineer",
            "status": "draft",
            "employment_type": None,
            "start_date": None,
            "salary_amount": 85000,
            "salary_currency": "GBP",
            "bonus_amount": 5000,
            "benefits": None,
            "expires_at": None,
            "notes": None,
            "id": uuid4(),
            "sent_at": None,
            "responded_at": None,
            "created_by": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        result = _offer_output(row, include_salary=False)
        self.assertIsNone(result.salary_amount)
        self.assertIsNone(result.salary_currency)
        self.assertIsNone(result.bonus_amount)


class PlacementFeePermissionTests(unittest.TestCase):
    def setUp(self):
        from datetime import date, datetime, timezone
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.row = {
            "organization_id": self.organization_id,
            "application_id": uuid4(),
            "offer_id": None,
            "job_id": uuid4(),
            "candidate_id": uuid4(),
            "client_id": None,
            "status": "active",
            "start_date": date(2026, 1, 1),
            "end_date": None,
            "fee_amount": 12000,
            "fee_currency": "GBP",
            "fee_type": "fixed",
            "fee_percentage": None,
            "notes": None,
            "id": uuid4(),
            "created_by": self.user_id,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

    def test_placement_fee_fields_redacted_without_fee_read_permission(self):
        from app.routers.placements import _placement_output
        def permission(_user, _org, key):
            if key == "placement.fee.read":
                raise HTTPException(403, "denied")
        with patch("app.routers.placements.require_permission", side_effect=permission):
            result = _placement_output(self.row, self.user_id, self.organization_id)
        self.assertIsNone(result.fee_amount)
        self.assertIsNone(result.fee_currency)
        self.assertIsNone(result.fee_type)
        self.assertIsNone(result.fee_percentage)

    def test_placement_fee_write_requires_separate_permission(self):
        from types import SimpleNamespace
        from app.routers.placements import _require_placement_write
        payload = SimpleNamespace(model_fields_set={"fee_amount"})
        with patch("app.routers.placements.require_permission") as permission:
            _require_placement_write(self.user_id, self.organization_id, payload)
        self.assertEqual(
            [call.args[2] for call in permission.call_args_list],
            ["placement.manage", "placement.fee.manage"],
        )

    def test_placement_non_fee_update_does_not_require_fee_permission(self):
        from types import SimpleNamespace
        from app.routers.placements import _require_placement_write
        payload = SimpleNamespace(model_fields_set={"status"})
        with patch("app.routers.placements.require_permission") as permission:
            _require_placement_write(self.user_id, self.organization_id, payload)
        permission.assert_called_once_with(self.user_id, self.organization_id, "placement.manage")


if __name__ == "__main__":
    unittest.main()
