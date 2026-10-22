import unittest
from datetime import date
from decimal import Decimal
from uuid import UUID
from unittest.mock import patch
from fastapi import HTTPException
from app.routers import requisitions as requisitions_router
from app.schemas.requisitions import RequisitionCreate, RequisitionUpdate

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")

class RequisitionSchemaTests(unittest.TestCase):
    def test_create_trims_text_and_defaults_headcount(self):
        payload = RequisitionCreate(organization_id=ORG, title=" Platform Engineer ", justification=" Backfill role ")
        self.assertEqual(payload.title, "Platform Engineer")
        self.assertEqual(payload.justification, "Backfill role")
        self.assertEqual(payload.headcount, 1)

    def test_rejects_non_positive_headcount(self):
        with self.assertRaises(ValueError):
            RequisitionCreate(organization_id=ORG, title="Engineer", justification="Growth", headcount=0)

    def test_rejects_invalid_salary_range(self):
        with self.assertRaises(ValueError):
            RequisitionCreate(organization_id=ORG, title="Engineer", justification="Growth", salary_min=Decimal("90000"), salary_max=Decimal("80000"))

    def test_rejects_close_date_before_start_date(self):
        with self.assertRaises(ValueError):
            RequisitionCreate(organization_id=ORG, title="Engineer", justification="Growth", target_start_date=date(2027,3,1), target_close_date=date(2027,2,1))

    def test_update_rejects_invalid_salary_range(self):
        with self.assertRaises(ValueError):
            RequisitionUpdate(salary_min=100, salary_max=50)

class RequisitionEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_requires_organisation_membership(self):
        with patch.object(requisitions_router, "assert_org_member", side_effect=HTTPException(403, "forbidden")):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.list_requisitions(ORG, None, None, 50, 0, USER)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_approval_requires_admin_role(self):
        rid = UUID("33333333-3333-4333-8333-333333333333")
        row = {"id": rid, "organization_id": ORG}
        with patch.object(requisitions_router, "authorised_row", return_value=row), patch.object(requisitions_router, "get_org_role", return_value="recruiter"):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.approve_requisition(rid, requisitions_router.DecisionBody(comment="Review"), USER)
        self.assertEqual(raised.exception.status_code, 403)
