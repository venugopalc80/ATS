import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.ai import GenerateInput, RecommendationInput, router


class AIRouterContractTests(unittest.TestCase):
    def test_router_registers_ai_endpoints(self):
        paths = {route.path for route in router.routes if hasattr(route, "path")}
        self.assertIn("/api/ai/assistant", paths)
        self.assertIn("/api/ai/governance/evaluations", paths)
        self.assertIn("/api/ai/job-description-versions/{version_id}/publish", paths)

    def test_generate_request_requires_valid_task(self):
        with self.assertRaises(ValueError):
            GenerateInput(organization_id=uuid4(), task="reject_candidate")

    def test_recommendation_requires_source_references_and_evidence(self):
        with self.assertRaises(ValueError):
            RecommendationInput(
                organization_id=uuid4(),
                object_type="candidate",
                object_id=uuid4(),
                purpose="A test recommendation purpose",
                input_references=[],
                evidence=[],
                explanation="A test explanation based on source data",
            )


class _NotFoundCursor:
    """Minimal cursor double: no record exists in the requested tenant."""
    def __init__(self):
        self.query = ""
        self.params = None
        self.calls = []

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        self.calls.append((query, params))

    def fetchone(self):
        return None


class TenantScopedEvidenceTests(unittest.TestCase):
    def test_each_evidence_lookup_is_scoped_to_requested_organization(self):
        from fastapi import HTTPException
        from app.routers.ai import _load_evidence

        org_id = uuid4()
        cases = [
            ("candidate", {"candidate_id": uuid4()}),
            ("job", {"job_id": uuid4()}),
            ("application", {"application_id": uuid4()}),
            ("interview", {"interview_id": uuid4()}),
            ("recommendation", {"recommendation_id": uuid4()}),
        ]

        for label, field in cases:
            with self.subTest(record_type=label):
                cursor = _NotFoundCursor()
                payload = GenerateInput(
                    organization_id=org_id,
                    task="answer_authorized_records",
                    **field,
                )
                with self.assertRaises(HTTPException) as caught:
                    _load_evidence(cursor, payload)

                self.assertEqual(caught.exception.status_code, 404)
                self.assertEqual(len(cursor.calls), 1)
                query, params = cursor.calls[0]
                self.assertIn("organization_id=%s", query.lower())
                self.assertEqual(params[-1], org_id)
                self.assertNotIn("select *", query.lower())

    def test_candidate_from_another_organization_is_not_returned_as_evidence(self):
        from fastapi import HTTPException
        from app.routers.ai import _load_evidence

        org_a = uuid4()
        candidate_owned_by_org_b = uuid4()
        cursor = _NotFoundCursor()
        payload = GenerateInput(
            organization_id=org_a,
            task="summarize_candidate",
            candidate_id=candidate_owned_by_org_b,
        )

        with self.assertRaises(HTTPException) as caught:
            _load_evidence(cursor, payload)

        self.assertEqual(caught.exception.status_code, 404)
        query, params = cursor.calls[0]
        self.assertIn("where id=%s and organization_id=%s", query.lower())
        self.assertEqual(params, [candidate_owned_by_org_b, org_a])




class AIRoleGuardTests(unittest.TestCase):
    def test_viewer_cannot_summarize_candidate(self):
        import asyncio
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.routers.ai import assistant

        organization_id = uuid4()
        user_id = uuid4()
        payload = GenerateInput(
            organization_id=organization_id,
            task="summarize_candidate",
            candidate_id=uuid4(),
        )
        with patch("app.routers.ai.assert_org_member") as member_check, \\
             patch("app.routers.ai.get_org_role", return_value="viewer"):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(assistant(payload, user_id=user_id))

        self.assertEqual(caught.exception.status_code, 403)
        member_check.assert_called_once_with(user_id, organization_id)

    def test_viewer_cannot_prepare_interview_questions(self):
        import asyncio
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.routers.ai import assistant

        organization_id = uuid4()
        payload = GenerateInput(
            organization_id=organization_id,
            task="interview_questions",
            job_id=uuid4(),
        )
        with patch("app.routers.ai.assert_org_member"), \\
             patch("app.routers.ai.get_org_role", return_value="viewer"):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(assistant(payload, user_id=uuid4()))

        self.assertEqual(caught.exception.status_code, 403)



if __name__ == "__main__":
    unittest.main()
