import unittest
from uuid import uuid4

from pydantic import ValidationError
from fastapi import HTTPException

from app.routers.collaboration import ConversationCreate, MessageCreate, _member, _check_org_members


class FakeCursor:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


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

    def test_member_helper_returns_join_date_for_authorized_member(self):
        joined_at = object()
        cursor = FakeCursor(one={"joined_at": joined_at})
        membership = _member(cursor, uuid4(), uuid4())
        self.assertIs(membership["joined_at"], joined_at)
        self.assertIn("organization_members", cursor.query)
        self.assertIn("cm.user_id=%s", cursor.query)
        self.assertIn("cm.left_at is null", cursor.query)
        self.assertIn("c.archived_at is null", cursor.query)

    def test_member_helper_hides_nonmember_conversation(self):
        with self.assertRaises(HTTPException) as error:
            _member(FakeCursor(one=None), uuid4(), uuid4())
        self.assertEqual(error.exception.status_code, 404)

    def test_organization_member_check_rejects_outsider(self):
        requested = [uuid4(), uuid4()]
        organization_id = uuid4()
        cursor = FakeCursor(many=[{"user_id": requested[0]}])
        with self.assertRaises(HTTPException) as error:
            _check_org_members(cursor, organization_id, requested)
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("organization_id=%s", cursor.query)
        self.assertEqual(cursor.params, [organization_id, requested])

    def test_organization_member_check_accepts_only_members_of_requested_org(self):
        organization_id = uuid4()
        requested = [uuid4(), uuid4()]
        cursor = FakeCursor(many=[{"user_id": user_id} for user_id in requested])

        _check_org_members(cursor, organization_id, requested)

        self.assertEqual(cursor.params, [organization_id, requested])
        self.assertIn("user_id = any(%s)", cursor.query)

    def test_message_enforces_maximum_length(self):
        with self.assertRaises(ValidationError):
            MessageCreate(body="x" * 10001)


if __name__ == "__main__":
    unittest.main()
