import unittest

from pydantic import ValidationError

from app.schemas.communications import (
    InternalNoteCreate,
    MessageDraftCreate,
    TemplateCreate,
    ThreadCreate,
)
from app.routers.notifications import ESSENTIAL_TYPES, PreferenceUpdate


class CommunicationSchemaTests(unittest.TestCase):
    def test_internal_note_requires_non_empty_body(self):
        with self.assertRaises(ValidationError):
            InternalNoteCreate(body_text="   ")

    def test_message_draft_rejects_internal_channel(self):
        with self.assertRaises(ValidationError):
            MessageDraftCreate(
                body_text="Interview details",
                channel="internal",
                recipient_address="candidate@example.com",
                idempotency_key="request-key-0001",
            )

    def test_message_draft_requires_idempotency_key(self):
        with self.assertRaises(ValidationError):
            MessageDraftCreate(
                body_text="Interview details",
                channel="email",
                recipient_address="candidate@example.com",
                idempotency_key="short",
            )

    def test_template_key_is_constrained(self):
        with self.assertRaises(ValidationError):
            TemplateCreate(
                organization_id="11111111-1111-4111-8111-111111111111",
                template_key="../unsafe",
                name="Interview",
                channel="email",
                body_text="Hello",
            )

    def test_thread_requires_application_and_organization(self):
        with self.assertRaises(ValidationError):
            ThreadCreate(application_id="not-a-uuid", organization_id="not-a-uuid")

    def test_preference_channel_is_limited_to_supported_channels(self):
        with self.assertRaises(ValidationError):
            PreferenceUpdate(
                organization_id="11111111-1111-4111-8111-111111111111",
                notification_type="interview_reminder",
                channel="push",
                enabled=False,
            )

    def test_essential_notification_types_are_explicit(self):
        self.assertIn("account_security", ESSENTIAL_TYPES)
        self.assertIn("password_reset", ESSENTIAL_TYPES)


if __name__ == "__main__":
    unittest.main()
