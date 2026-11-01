import asyncio
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

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



from app.routers import candidate_portal


class _FakeCursor:
    def __init__(self, responses, statements):
        self.responses = responses
        self.statements = statements
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.statements.append((query, params))
        self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current


class _FakeConnection:
    def __init__(self, responses, statements):
        self.cursor_value = _FakeCursor(responses, statements)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class CandidatePortalDocumentOwnershipTests(unittest.TestCase):
    def test_download_scopes_document_to_authenticated_candidate_and_tenant(self):
        user_id, organization_id, candidate_id, document_id = [uuid4() for _ in range(4)]
        statements = []
        document = {
            "storage_bucket": "candidate-documents",
            "storage_path": "private/org/candidate/file.pdf",
            "original_filename": "resume.pdf",
        }
        responses = [
            {"candidate_id": candidate_id},
            document,
        ]

        @contextmanager
        def connection_factory():
            yield _FakeConnection(responses, statements)

        storage = SimpleNamespace(
            create_signed_url=lambda path, ttl, options: {"signedURL": "https://signed.example/file"}
        )
        storage_client = SimpleNamespace(
            storage=SimpleNamespace(from_=lambda bucket: storage)
        )
        user = SimpleNamespace(id=user_id)

        with patch.object(candidate_portal, "get_connection", side_effect=connection_factory), \
             patch("app.routers.documents.storage_client", return_value=storage_client):
            result = asyncio.run(candidate_portal.create_candidate_document_download(
                document_id=document_id,
                organization_id=organization_id,
                user=user,
            ))

        self.assertEqual(result["url"], "https://signed.example/file")
        document_query, params = statements[1]
        self.assertIn("id=%s and organization_id=%s and candidate_id=%s", document_query)
        self.assertIn("deleted_at is null", document_query)
        self.assertEqual(params, [document_id, organization_id, candidate_id])

    def test_download_returns_not_found_for_document_outside_candidate_scope(self):
        user_id, organization_id, candidate_id, document_id = [uuid4() for _ in range(4)]
        statements = []
        responses = [{"candidate_id": candidate_id}, None]

        @contextmanager
        def connection_factory():
            yield _FakeConnection(responses, statements)

        user = SimpleNamespace(id=user_id)
        with patch.object(candidate_portal, "get_connection", side_effect=connection_factory), \
             patch("app.routers.documents.storage_client") as storage_client:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(candidate_portal.create_candidate_document_download(
                    document_id=document_id,
                    organization_id=organization_id,
                    user=user,
                ))
        self.assertEqual(raised.exception.status_code, 404)
        storage_client.assert_not_called()




if __name__ == "__main__":
    unittest.main()
