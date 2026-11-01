import unittest
from types import SimpleNamespace

from app.routers.candidate_portal import _verified_email


class CandidatePortalIdentityTests(unittest.TestCase):
    def test_verified_email_is_normalized(self):
        user = SimpleNamespace(email=" Candidate@Example.com ", email_confirmed_at="2026-10-01T10:00:00Z")
        self.assertEqual(_verified_email(user), "candidate@example.com")

    def test_unverified_email_cannot_link(self):
        user = SimpleNamespace(email="candidate@example.com", email_confirmed_at=None, confirmed_at=None)
        self.assertIsNone(_verified_email(user))

    def test_missing_or_malformed_email_cannot_link(self):
        self.assertIsNone(_verified_email(SimpleNamespace(email=None, email_confirmed_at="2026-10-01")))
        self.assertIsNone(_verified_email(SimpleNamespace(email="not-an-email", email_confirmed_at="2026-10-01")))


if __name__ == "__main__":
    unittest.main()


from datetime import datetime, timezone
from uuid import uuid4

from app.routers.candidate_portal import _candidate_document_payload


class CandidatePortalDocumentTests(unittest.TestCase):
    def test_document_payload_contains_only_candidate_safe_metadata(self):
        document_id = uuid4()
        row = {
            "id": document_id,
            "application_id": None,
            "document_type": "cv",
            "original_filename": "resume.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1024,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
            "storage_bucket": "candidate-documents",
            "storage_path": "org/candidate/private.pdf",
            "sha256": "secret-digest",
            "candidate_id": uuid4(),
            "organization_id": uuid4(),
        }
        payload = _candidate_document_payload(row)
        self.assertEqual(payload["id"], document_id)
        self.assertEqual(payload["original_filename"], "resume.pdf")
        self.assertNotIn("storage_path", payload)
        self.assertNotIn("storage_bucket", payload)
        self.assertNotIn("sha256", payload)
        self.assertNotIn("candidate_id", payload)
        self.assertNotIn("application_id", payload)
        self.assertNotIn("organization_id", payload)


if __name__ == "__main__":
    unittest.main()
