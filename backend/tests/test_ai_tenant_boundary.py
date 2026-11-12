"""Tenant-boundary regression tests for the Section 7 AI assistant API.

These tests prove the API rejects a caller who is not a member of the requested
organisation before checking roles, opening the database, or calling an AI provider.
They are not a substitute for a live two-identity Supabase RLS test.
"""
import asyncio
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers.ai import GenerateInput, assistant


class AIAssistantTenantBoundaryTests(unittest.TestCase):
    def test_non_member_cannot_use_another_organisation_id(self):
        requested_organisation_id = uuid4()
        user_id = uuid4()
        payload = GenerateInput(
            organization_id=requested_organisation_id,
            task="summarize_candidate",
            candidate_id=uuid4(),
        )

        with patch(
            "app.routers.ai.assert_org_member",
            side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
        ) as membership_check:
            with patch("app.routers.ai.get_org_role") as role_lookup:
                with patch("app.routers.ai.get_connection") as database:
                    with patch("app.routers.ai.generate_text") as provider:
                        with self.assertRaises(HTTPException) as caught:
                            asyncio.run(assistant(payload, user_id=user_id))

        self.assertEqual(caught.exception.status_code, 403)
        membership_check.assert_called_once_with(user_id, requested_organisation_id)
        role_lookup.assert_not_called()
        database.assert_not_called()
        provider.assert_not_called()


    def test_non_member_cannot_submit_feedback_to_another_organisation_run(self):
        from app.routers.ai import FeedbackInput, feedback

        requested_organisation_id = uuid4()
        user_id = uuid4()
        run_id = uuid4()
        payload = FeedbackInput(
            organization_id=requested_organisation_id,
            feedback_status="unsafe",
            feedback_text="Synthetic cross-tenant feedback attempt",
        )

        with patch(
            "app.routers.ai.assert_org_member",
            side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
        ) as membership_check:
            with patch("app.routers.ai.get_connection") as database:
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(feedback(run_id, payload, user_id=user_id))

        self.assertEqual(caught.exception.status_code, 403)
        membership_check.assert_called_once_with(user_id, requested_organisation_id)
        database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
