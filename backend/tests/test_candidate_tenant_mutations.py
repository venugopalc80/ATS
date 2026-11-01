import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.schemas.candidates import CandidateUpdate
from app.services.candidate_service import CandidateService


ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")


class CandidateTenantMutationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.__enter__.return_value = self.connection
        self.connection.__exit__.return_value = False
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection.cursor.return_value.__exit__.return_value = False
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.connection_context.__exit__.return_value = False

    async def test_candidate_read_requires_membership_in_candidate_organisation(self):
        self.cursor.fetchone.return_value = None
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            result = await CandidateService().get_candidate_for_member(CANDIDATE, OTHER_ORG)

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("from public.candidates c", sql.lower())
        self.assertIn("from public.organization_members om", sql.lower())
        self.assertIn("om.organization_id = c.organization_id", sql)
        self.assertIn("om.user_id = %s", sql)
        self.assertEqual(params, [CANDIDATE, OTHER_ORG])
        self.assertIsNone(result)

    async def test_update_query_scopes_candidate_id_and_organization_id(self):
        self.cursor.fetchone.return_value = {"id": CANDIDATE, "organization_id": ORG}
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            result = await CandidateService().update_candidate(
                CANDIDATE, ORG, CandidateUpdate(first_name="Updated")
            )

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("where id = %s and organization_id = %s", sql.lower())
        self.assertEqual(params, ["Updated", CANDIDATE, ORG])
        self.assertEqual(result["organization_id"], ORG)

    async def test_update_returns_no_row_when_candidate_is_not_in_organization(self):
        self.cursor.fetchone.return_value = None
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            result = await CandidateService().update_candidate(
                CANDIDATE, OTHER_ORG, CandidateUpdate(first_name="Tampered")
            )

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("where id = %s and organization_id = %s", sql.lower())
        self.assertEqual(params, ["Tampered", CANDIDATE, OTHER_ORG])
        self.assertIsNone(result)

    async def test_no_op_update_read_is_also_tenant_scoped(self):
        self.cursor.fetchone.return_value = None
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            result = await CandidateService().update_candidate(
                CANDIDATE, OTHER_ORG, CandidateUpdate()
            )

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("where id = %s and organization_id = %s", sql.lower())
        self.assertEqual(params, [CANDIDATE, OTHER_ORG])
        self.assertIsNone(result)

    async def test_delete_query_scopes_candidate_id_and_organization_id(self):
        self.cursor.rowcount = 1
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            deleted = await CandidateService().delete_candidate(CANDIDATE, ORG)

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("where id = %s and organization_id = %s", sql.lower())
        self.assertEqual(params, [CANDIDATE, ORG])
        self.assertTrue(deleted)

    async def test_delete_does_not_delete_candidate_from_another_organization(self):
        self.cursor.rowcount = 0
        with patch("app.services.candidate_service.get_connection", return_value=self.connection_context):
            deleted = await CandidateService().delete_candidate(CANDIDATE, OTHER_ORG)

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("where id = %s and organization_id = %s", sql.lower())
        self.assertEqual(params, [CANDIDATE, OTHER_ORG])
        self.assertFalse(deleted)


if __name__ == "__main__":
    unittest.main()
