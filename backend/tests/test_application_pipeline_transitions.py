import unittest
from unittest.mock import patch
from uuid import UUID

from app.schemas.applications import ApplicationTransition
from app.services.application_service import ALLOWED_APPLICATION_TRANSITIONS


class ApplicationPipelineTransitionTests(unittest.TestCase):
    def test_supported_pipeline_stages_include_configurable_workflow_stages(self):
        self.assertIn("applied", ALLOWED_APPLICATION_TRANSITIONS)
        self.assertIn("shortlisted", ALLOWED_APPLICATION_TRANSITIONS["screening"])
        self.assertIn("assessment", ALLOWED_APPLICATION_TRANSITIONS["interview"])

    def test_terminal_stages_cannot_transition(self):
        for stage in ("hired", "rejected", "withdrawn"):
            self.assertEqual(ALLOWED_APPLICATION_TRANSITIONS[stage], set())

    def test_invalid_backward_transition_is_not_permitted(self):
        self.assertNotIn("screening", ALLOWED_APPLICATION_TRANSITIONS["offer"])

    def test_transition_reason_is_bounded(self):
        with self.assertRaises(Exception):
            ApplicationTransition(status="screening", reason="x" * 1001)


if __name__ == "__main__":
    unittest.main()
