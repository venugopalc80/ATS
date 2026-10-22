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


    def test_update_accepts_partial_reassignment_fields(self):
        payload = RequisitionUpdate(recruiter_id=USER, hiring_manager_id=None)
        self.assertEqual(payload.recruiter_id, USER)
        self.assertIsNone(payload.hiring_manager_id)

    def test_update_rejects_blank_title(self):
        with self.assertRaises(ValueError):
            RequisitionUpdate(title="   ")


class RequisitionLifecycleEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_is_restricted_to_draft_or_rejected(self):
        rid = UUID("33333333-3333-4333-8333-333333333333")
        row = {"id": rid, "organization_id": ORG, "status": "pending_approval", "requested_by": USER}
        with patch.object(requisitions_router, "authorised_row", return_value=row):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.update_requisition(rid, RequisitionUpdate(title="Updated"), USER)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_submit_rejects_non_requester_without_admin_role(self):
        rid = UUID("33333333-3333-4333-8333-333333333333")
        other_user = UUID("44444444-4444-4444-8444-444444444444")
        row = {"id": rid, "organization_id": ORG, "status": "draft", "requested_by": other_user}
        with patch.object(requisitions_router, "authorised_row", return_value=row), patch.object(requisitions_router, "get_org_role", return_value="recruiter"):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.submit_requisition(rid, USER)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_approval_conflict_when_not_pending(self):
        rid = UUID("33333333-3333-4333-8333-333333333333")
        row = {"id": rid, "organization_id": ORG, "status": "approved"}
        with patch.object(requisitions_router, "authorised_row", return_value=row), patch.object(requisitions_router, "get_org_role", return_value="admin"), patch.object(requisitions_router.service, "decide", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.approve_requisition(rid, requisitions_router.DecisionBody(comment="Looks good"), USER)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_conversion_rejects_non_approver_role(self):
        rid = UUID("33333333-3333-4333-8333-333333333333")
        row = {"id": rid, "organization_id": ORG, "status": "approved"}
        with patch.object(requisitions_router, "authorised_row", return_value=row), patch.object(requisitions_router, "get_org_role", return_value="hiring_manager"):
            with self.assertRaises(HTTPException) as raised:
                await requisitions_router.convert_to_job(rid, USER)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_cross_organisation_client_link_is_rejected(self):
        client_id = UUID("55555555-5555-4555-8555-555555555555")
        cursor = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        cursor.fetchone.return_value = None
        connection = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(requisitions_router, "get_connection", return_value=connection):
            with self.assertRaises(HTTPException) as raised:
                requisitions_router.validate_org_links(ORG, client_id, None, None)
        self.assertEqual(raised.exception.status_code, 422)


class RequisitionServiceAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_audit_records_old_and_new_values(self):
        from unittest.mock import MagicMock
        from app.services import requisition_service as service_module

        rid = UUID("33333333-3333-4333-8333-333333333333")
        before = {"id": rid, "organization_id": ORG, "title": "Old title"}
        after = {"id": rid, "organization_id": ORG, "title": "New title"}
        cursor = MagicMock()
        cursor.fetchone.side_effect = [before, after]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(service_module, "get_connection", return_value=connection), patch.object(service_module, "audit") as audit_mock:
            await service_module.RequisitionService().update_requisition(rid, RequisitionUpdate(title="New title"), USER)
        self.assertEqual(audit_mock.call_args.args[2], USER)
        self.assertEqual(audit_mock.call_args.args[4], rid)
        self.assertEqual(audit_mock.call_args.args[5], {"changes": {"title": {"old": "Old title", "new": "New title"}}})
