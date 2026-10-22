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
        with patch.object(requisitions_router, "authorised_row", return_value=row), patch.object(requisitions_router, "get_org_role", return_value="recruiter"):
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
        from unittest.mock import MagicMock
        client_id = UUID("55555555-5555-4555-8555-555555555555")
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        connection = MagicMock()
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
        previous_recruiter = UUID("77777777-7777-4777-8777-777777777777")
        next_recruiter = UUID("88888888-8888-4888-8888-888888888888")
        before = {"id": rid, "organization_id": ORG, "title": "Old title", "recruiter_id": previous_recruiter}
        after = {"id": rid, "organization_id": ORG, "title": "New title", "recruiter_id": next_recruiter}
        cursor = MagicMock()
        cursor.fetchone.side_effect = [before, after]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(service_module, "get_connection", return_value=connection), patch.object(service_module, "audit") as audit_mock:
            await service_module.RequisitionService().update_requisition(rid, RequisitionUpdate(title="New title", recruiter_id=next_recruiter), USER)
        self.assertEqual(audit_mock.call_args.args[2], USER)
        self.assertEqual(audit_mock.call_args.args[4], rid)
        self.assertEqual(audit_mock.call_args.args[5], {"changes": {"title": {"old": "Old title", "new": "New title"}, "recruiter_id": {"old": "77777777-7777-4777-8777-777777777777", "new": "88888888-8888-4888-8888-888888888888"}}})

class RequisitionAssignmentTests(unittest.TestCase):
    def test_viewer_cannot_be_assigned_as_recruiter(self):
        from unittest.mock import MagicMock
        cursor = MagicMock()
        cursor.fetchone.return_value = {"role": "viewer"}
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(requisitions_router, "get_connection", return_value=connection):
            with self.assertRaises(HTTPException) as raised:
                requisitions_router.validate_org_links(ORG, None, None, USER)
        self.assertEqual(raised.exception.status_code, 422)

    def test_non_member_cannot_be_assigned_as_hiring_manager(self):
        from unittest.mock import MagicMock
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(requisitions_router, "get_connection", return_value=connection):
            with self.assertRaises(HTTPException) as raised:
                requisitions_router.validate_org_links(ORG, None, USER, None)
        self.assertEqual(raised.exception.status_code, 422)

class RequisitionConversionRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_conversion_returns_existing_job_without_inserting(self):
        from unittest.mock import MagicMock
        from app.services import requisition_service as service_module
        rid = UUID("33333333-3333-4333-8333-333333333333")
        job_id = UUID("66666666-6666-4666-8666-666666666666")
        converted = {"id": rid, "status": "converted", "job_id": job_id}
        job = {"id": job_id, "organization_id": ORG, "job_code": "REQ-12345678", "title": "Engineer", "status": "draft"}
        cursor = MagicMock()
        cursor.fetchone.side_effect = [converted, job]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(service_module, "get_connection", return_value=connection):
            result = await service_module.RequisitionService().convert_to_job(rid, USER)
        self.assertTrue(result["already_converted"])
        self.assertEqual(result["job"], job)
        self.assertFalse(any("insert into public.jobs" in str(call).lower() for call in cursor.execute.call_args_list))

class RequisitionListQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_query_scopes_organisation_and_applies_limit_offset(self):
        from unittest.mock import MagicMock
        from app.services import requisition_service as service_module
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"id": UUID("33333333-3333-4333-8333-333333333333")}]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(service_module, "get_connection", return_value=connection):
            result = await service_module.RequisitionService().list_requisitions(ORG, None, None, 25, 50)
        self.assertEqual(len(result), 1)
        sql = cursor.execute.call_args.args[0].lower()
        params = cursor.execute.call_args.args[1]
        self.assertIn("where organization_id=%s", sql)
        self.assertIn("limit %s offset %s", sql)
        self.assertEqual(params, [ORG, 25, 50])

    async def test_list_query_combines_status_and_search_without_losing_tenant_scope(self):
        from unittest.mock import MagicMock
        from app.services import requisition_service as service_module
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        with patch.object(service_module, "get_connection", return_value=connection):
            result = await service_module.RequisitionService().list_requisitions(ORG, "draft", "platform", 10, 20)
        self.assertEqual(result, [])
        sql = cursor.execute.call_args.args[0].lower()
        params = cursor.execute.call_args.args[1]
        self.assertIn("where organization_id=%s", sql)
        self.assertIn("and status=%s", sql)
        self.assertIn("title ilike %s or requisition_code ilike %s or department ilike %s", sql)
        self.assertEqual(params, [ORG, "draft", "%platform%", "%platform%", "%platform%", 10, 20])
