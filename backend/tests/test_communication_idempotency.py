"""Idempotency safeguards for candidate message drafts."""

import unittest
from uuid import UUID

from app.routers.communications import _same_draft_request

THREAD = UUID("22222222-2222-4222-8222-222222222222")
TEMPLATE = UUID("44444444-4444-4444-8444-444444444444")


def message(**overrides):
    row = {
        "thread_id": THREAD,
        "visibility": "candidate",
        "status": "draft",
        "body_text": "Hello there",
        "subject": "Interview follow-up",
        "channel": "email",
        "template_id": TEMPLATE,
        "template_version": 2,
    }
    row.update(overrides)
    return row


class DraftIdempotencyTests(unittest.TestCase):
    def check_same(self, row):
        return _same_draft_request(
            row,
            {"recipient_address": "candidate@example.com"},
            thread_id=THREAD,
            body_text=" Hello there ",
            subject="Interview follow-up",
            channel="email",
            template_id=TEMPLATE,
            template_version=2,
            recipient_address=" candidate@example.com ",
        )

    def test_matching_draft_retry_is_idempotent(self):
        self.assertTrue(self.check_same(message()))

    def test_same_key_cannot_replay_non_draft_message(self):
        self.assertFalse(self.check_same(message(status="sent")))

    def test_same_key_cannot_replay_internal_note(self):
        self.assertFalse(self.check_same(message(visibility="internal", status="internal")))


if __name__ == "__main__":
    unittest.main()
