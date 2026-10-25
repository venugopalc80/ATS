import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.routers.collaboration import ConversationCreate, MessageCreate


class CollaborationPayloadTests(unittest.TestCase):
    def test_direct_conversation_requires_one_other_member(self):
        with self.assertRaises(ValidationError):
            ConversationCreate(
                organization_id=uuid4(),
                kind="direct",
                member_ids=[uuid4(), uuid4()],
            )

    def test_direct_conversation_accepts_one_member(self):
        payload = ConversationCreate(
            organization_id=uuid4(),
            kind="direct",
            member_ids=[uuid4()],
        )
        self.assertEqual(payload.kind, "direct")
        self.assertEqual(len(payload.member_ids), 1)

    def test_group_conversation_requires_a_nonblank_title(self):
        with self.assertRaises(ValidationError):
            ConversationCreate(
                organization_id=uuid4(),
                kind="group",
                member_ids=[uuid4()],
                title="   ",
            )

    def test_group_conversation_accepts_title_and_members(self):
        payload = ConversationCreate(
            organization_id=uuid4(),
            kind="group",
            member_ids=[uuid4(), uuid4()],
            title="Hiring team",
        )
        self.assertEqual(payload.title, "Hiring team")

    def test_message_rejects_whitespace_only_body(self):
        with self.assertRaises(ValidationError):
            MessageCreate(body="   ")

    def test_message_accepts_body_and_idempotency_key(self):
        key = uuid4()
        payload = MessageCreate(body="Please review the shortlist", client_message_id=key)
        self.assertEqual(payload.body, "Please review the shortlist")
        self.assertEqual(payload.client_message_id, key)

    def test_message_enforces_maximum_length(self):
        with self.assertRaises(ValidationError):
            MessageCreate(body="x" * 10001)


if __name__ == "__main__":
    unittest.main()
