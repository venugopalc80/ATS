import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.assessments import router


class AssessmentProviderWebhookTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_missing_provider_secret_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                "/api/assessments/providers/vendor_a/webhook",
                content=b'{"assignment_id":"00000000-0000-0000-0000-000000000001","methodology":"rubric"}',
                headers={"X-Assessment-Event-Id": "evt-1", "X-Assessment-Signature": "sha256=bad"},
            )
        self.assertEqual(response.status_code, 503)

    def test_invalid_signature_is_rejected_before_database_access(self):
        body = b'{"assignment_id":"00000000-0000-0000-0000-000000000001","methodology":"rubric"}'
        with patch.dict(os.environ, {"ASSESSMENT_PROVIDER_VENDOR_A_WEBHOOK_SECRET": "test-secret"}, clear=True):
            response = self.client.post(
                "/api/assessments/providers/vendor_a/webhook",
                content=body,
                headers={"X-Assessment-Event-Id": "evt-1", "X-Assessment-Signature": "sha256=invalid"},
            )
        self.assertEqual(response.status_code, 401)

    def test_valid_signature_uses_raw_request_body(self):
        body = b'{"assignment_id":"00000000-0000-0000-0000-000000000001","methodology":"rubric"}'
        signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"ASSESSMENT_PROVIDER_VENDOR_A_WEBHOOK_SECRET": "test-secret"}, clear=True):
            # The request reaches payload/database processing, so a configured database is then required.
            response = self.client.post(
                "/api/assessments/providers/vendor_a/webhook",
                content=body,
                headers={"X-Assessment-Event-Id": "evt-1", "X-Assessment-Signature": signature},
            )
        self.assertNotEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
