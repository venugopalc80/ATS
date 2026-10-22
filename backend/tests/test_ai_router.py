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


if __name__ == "__main__":
    unittest.main()
