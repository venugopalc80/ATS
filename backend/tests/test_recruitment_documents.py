import hashlib
import hmac
import unittest

from fastapi import HTTPException

import inspect

from app.routers.recruitment_documents import (
    _template_body, _validate_recruitment_file, next_signer_status,
    receive_normalized_signature_event, require_document_manager_role,
    verify_adapter_signature,
)



class RecruitmentDocumentPermissionTests(unittest.TestCase):
    def test_allows_hiring_roles(self):
        for role in ("owner", "admin", "recruiter", "hiring_manager"):
            with self.subTest(role=role):
                require_document_manager_role(role)

    def test_denies_non_hiring_roles(self):
        for role in ("interviewer", "candidate", "member", "viewer"):
            with self.subTest(role=role):
                with self.assertRaises(HTTPException) as error:
                    require_document_manager_role(role)
                self.assertEqual(error.exception.status_code, 403)



class RecruitmentSignatureTransitionTests(unittest.TestCase):
    def test_webhook_locks_document_before_signer_to_serialize_events(self):
        source = inspect.getsource(receive_normalized_signature_event)
        document_lock = source.index("where id=%s\\n               for update")
        signer_lock = source.index("where document_id=%s and organization_id=%s and lower(email)=lower(%s)\\n               for update")
        self.assertLess(document_lock, signer_lock)

    def test_progression_is_monotonic_for_out_of_order_events(self):
        self.assertEqual(next_signer_status("viewed", "sent"), "viewed")
        self.assertEqual(next_signer_status("signed", "viewed"), "signed")
        self.assertEqual(next_signer_status("sent", "viewed"), "viewed")

    def test_terminal_states_cannot_be_reversed(self):
        for terminal in ("signed", "declined", "expired", "revoked"):
            with self.subTest(terminal=terminal):
                self.assertEqual(next_signer_status(terminal, "sent"), terminal)
                self.assertEqual(next_signer_status(terminal, "viewed"), terminal)
                self.assertEqual(next_signer_status(terminal, "signed"), terminal)

    def test_terminal_event_closes_active_signer(self):
        self.assertEqual(next_signer_status("pending", "declined"), "declined")
        self.assertEqual(next_signer_status("viewed", "expired"), "expired")
        self.assertEqual(next_signer_status("sent", "revoked"), "revoked")

    def test_unknown_existing_state_is_not_replaced(self):
        self.assertEqual(next_signer_status("unexpected", "signed"), "unexpected")


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
