import asyncio
import unittest

from fastapi import HTTPException
from uuid import UUID

from pydantic import ValidationError

from app.routers.communications import _same_draft_request
from app.schemas.communications import (
    InternalNoteCreate,
    MessageDraftCreate,
    TemplateCreate,
    ThreadCreate,
)
from app.routers.notifications import ESSENTIAL_TYPES, PreferenceUpdate, update_preference


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

    def test_essential_notification_preferences_cannot_be_disabled(self):
        payload = PreferenceUpdate(
            organization_id="11111111-1111-4111-8111-111111111111",
            notification_type="account_security",
            channel="email",
            enabled=False,
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(update_preference(
                payload,
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            ))
        self.assertEqual(raised.exception.status_code, 422)

    def test_security_namespace_preferences_cannot_be_disabled(self):
        payload = PreferenceUpdate(
            organization_id="11111111-1111-4111-8111-111111111111",
            notification_type="security.session_expiring",
            channel="in_app",
            enabled=False,
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(update_preference(
                payload,
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            ))
        self.assertEqual(raised.exception.status_code, 422)

    def test_essential_namespace_preferences_cannot_be_disabled(self):
        payload = PreferenceUpdate(
            organization_id="11111111-1111-4111-8111-111111111111",
            notification_type="account_security.device_changed",
            channel="email",
            enabled=False,
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(update_preference(
                payload,
                user_id=UUID("22222222-2222-4222-8222-222222222222"),
            ))
        self.assertEqual(raised.exception.status_code, 422)

    def test_idempotent_retry_requires_same_thread_and_template(self):
        thread_id = UUID("11111111-1111-4111-8111-111111111111")
        other_thread_id = UUID("22222222-2222-4222-8222-222222222222")
        template_id = UUID("33333333-3333-4333-8333-333333333333")
        message = {
            "thread_id": thread_id,
            "body_text": "Interview details",
            "subject": "Interview",
            "channel": "email",
            "template_id": template_id,
            "template_version": 2,
        }
        recipient = {"recipient_address": "candidate@example.com"}
        request = {
            "body_text": " Interview details ",
            "subject": "Interview",
            "channel": "email",
            "template_id": template_id,
            "template_version": 2,
            "recipient_address": "candidate@example.com",
        }

        self.assertTrue(_same_draft_request(message, recipient, thread_id=thread_id, **request))
        self.assertFalse(_same_draft_request(message, recipient, thread_id=other_thread_id, **request))
        self.assertFalse(
            _same_draft_request(
                message, recipient, thread_id=thread_id,
                **{**request, "template_version": 1},
            )
        )

    def test_idempotent_retry_requires_same_recipient(self):
        thread_id = UUID("11111111-1111-4111-8111-111111111111")
        message = {
            "thread_id": thread_id,
            "body_text": "Interview details",
            "subject": None,
            "channel": "email",
            "template_id": None,
            "template_version": None,
        }
        self.assertFalse(
            _same_draft_request(
                message, {"recipient_address": "first@example.com"},
                thread_id=thread_id,
                body_text="Interview details",
                subject=None,
                channel="email",
                template_id=None,
                template_version=None,
                recipient_address="second@example.com",
            )
        )


if __name__ == "__main__":
    unittest.main()
