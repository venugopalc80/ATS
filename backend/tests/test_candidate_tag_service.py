import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.candidate_tag_service import CandidateTagService


class CandidateTagServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = CandidateTagService()
        self.organization_id = uuid4()
        self.candidate_id = uuid4()
        self.tag_id = uuid4()
        self.user_id = uuid4()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.__enter__.return_value = self.connection
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection.cursor.return_value.__exit__.return_value = False
        self.connection.__exit__.return_value = False

    async def test_assignment_checks_candidate_and_tag_in_same_org_before_insert(self):
        self.cursor.fetchone.return_value = {"candidate_ok": False, "tag_ok": True}
        with patch("app.services.candidate_tag_service.get_connection") as get_connection:
            get_connection.return_value.__enter__.return_value = self.connection
            get_connection.return_value.__exit__.return_value = False
            with self.assertRaisesRegex(ValueError, "same organisation"):
                await self.service.assign_tag(
                    self.organization_id, self.candidate_id, self.tag_id, self.user_id
                )

        self.cursor.execute.assert_called_once()
        query, params = self.cursor.execute.call_args.args
        self.assertIn("public.candidates", query)
        self.assertIn("public.candidate_tags", query)
        self.assertEqual(
            params,
            [self.candidate_id, self.organization_id, self.tag_id, self.organization_id],
        )

    async def test_list_assignments_is_scoped_to_requested_org(self):
        expected = [{"candidate_id": self.candidate_id, "tag_id": self.tag_id, "name": "Shortlist", "colour": "#64748b"}]
        self.cursor.fetchall.return_value = expected
        with patch("app.services.candidate_tag_service.get_connection") as get_connection:
            get_connection.return_value.__enter__.return_value = self.connection
            get_connection.return_value.__exit__.return_value = False
            result = await self.service.list_candidate_assignments(self.organization_id)

        self.assertEqual(result, expected)
        query, params = self.cursor.execute.call_args.args
        self.assertIn("where a.organization_id = %s", query)
        self.assertIn("t.organization_id = a.organization_id", query)
        self.assertEqual(params, [self.organization_id])

    async def test_list_tags_scopes_candidate_filter_to_org(self):
        self.cursor.fetchall.return_value = []
        with patch("app.services.candidate_tag_service.get_connection") as get_connection:
            get_connection.return_value.__enter__.return_value = self.connection
            get_connection.return_value.__exit__.return_value = False
            result = await self.service.list_tags(self.organization_id, self.candidate_id)

        self.assertEqual(result, [])
        query, params = self.cursor.execute.call_args.args
        self.assertIn("where organization_id = %s", query)
        self.assertIn("a.organization_id = candidate_tags.organization_id", query)
        self.assertEqual(params, [self.organization_id, self.candidate_id])


if __name__ == "__main__":
    unittest.main()
