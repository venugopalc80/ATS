import hashlib
import hmac
import unittest

from fastapi import HTTPException

from app.routers.recruitment_documents import _template_body, _validate_recruitment_file, verify_adapter_signature


class RecruitmentDocumentTemplateTests(unittest.TestCase):
    def test_accepts_approved_placeholders_and_returns_sha256(self):
        body = "Dear {{ candidate.first_name }}, your role is {{job.title}}."
        placeholders, digest = _template_body(body)
        self.assertEqual(placeholders, ["candidate.first_name", "job.title"])
        self.assertEqual(digest, hashlib.sha256(body.encode()).hexdigest())

    def test_rejects_unapproved_placeholder(self):
        with self.assertRaises(HTTPException) as error:
            _template_body("{{candidate.date_of_birth}}")
        self.assertEqual(error.exception.status_code, 422)

    def test_rejects_malformed_placeholder(self):
        with self.assertRaises(HTTPException):
            _template_body("{{candidate.first_name")

    def test_valid_adapter_signature(self):
        secret = "test-secret"
        timestamp = "1792670400"
        raw = b'{"event_id":"evt-1"}'
        signed = timestamp.encode() + b"." + raw
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        self.assertTrue(verify_adapter_signature(raw, timestamp, "sha256=" + signature, secret, now=1792670400))

    def test_rejects_modified_body(self):
        secret = "test-secret"
        timestamp = "1792670400"
        signed = timestamp.encode() + b"." + b'{"event_id":"evt-1"}'
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        self.assertFalse(verify_adapter_signature(b'{"event_id":"evt-2"}', timestamp, signature, secret, now=1792670400))

    def test_rejects_stale_timestamp(self):
        self.assertFalse(verify_adapter_signature(b"{}", "1000", "00", "secret", now=2000))

    def test_rejects_invalid_timestamp(self):
        self.assertFalse(verify_adapter_signature(b"{}", "not-a-time", "00", "secret", now=2000))


    def test_accepts_pdf_upload_signature(self):
        self.assertEqual(_validate_recruitment_file(b"%PDF-1.7 body", "application/pdf"), ".pdf")

    def test_accepts_docx_upload_signature(self):
        self.assertEqual(
            _validate_recruitment_file(b"PK\x03\x04body", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ".docx",
        )

    def test_rejects_wrong_file_signature(self):
        with self.assertRaises(HTTPException) as error:
            _validate_recruitment_file(b"not a pdf", "application/pdf")
        self.assertEqual(error.exception.status_code, 415)

    def test_rejects_unsupported_upload_type(self):
        with self.assertRaises(HTTPException) as error:
            _validate_recruitment_file(b"hello", "text/plain")
        self.assertEqual(error.exception.status_code, 415)


if __name__ == "__main__":
    unittest.main()
