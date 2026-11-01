import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.routers.collaboration import _assert_group_owner, _add_or_reactivate_group_member


class FakeCursor:
    def __init__(self, one=None, rowcount=1):
        self.one = one
        self.rowcount = rowcount
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.one


class CollaborationAuthorizationTests(unittest.TestCase):
    def test_group_owner_check_is_scoped_to_current_organization_membership(self):
        cursor = FakeCursor(one={"kind": "group", "member_role": "owner"})
        conversation_id, user_id = uuid4(), uuid4()

        _assert_group_owner(cursor, conversation_id, user_id)

        self.assertIn("join public.organization_members", cursor.query)
        self.assertIn("cm.left_at is null", cursor.query)
        self.assertIn("c.archived_at is null", cursor.query)
        self.assertEqual(cursor.params, [conversation_id, user_id])

    def test_non_owner_cannot_manage_group_members(self):
        cursor = FakeCursor(one={"kind": "group", "member_role": "member"})

        with self.assertRaises(HTTPException) as error:
            _assert_group_owner(cursor, uuid4(), uuid4())

        self.assertEqual(error.exception.status_code, 403)

    def test_direct_conversation_cannot_be_managed_as_group(self):
        cursor = FakeCursor(one={"kind": "direct", "member_role": "owner"})

        with self.assertRaises(HTTPException) as error:
            _assert_group_owner(cursor, uuid4(), uuid4())

        self.assertEqual(error.exception.status_code, 403)


    def test_active_member_is_not_rejoined_or_reset(self):
        cursor = FakeCursor(rowcount=0)
        conversation_id, target_id = uuid4(), uuid4()

        added = _add_or_reactivate_group_member(cursor, conversation_id, target_id)

        self.assertFalse(added)
        self.assertIn("where public.conversation_members.left_at is not null", cursor.query)
        self.assertEqual(cursor.params, [conversation_id, target_id])

    def test_previously_removed_member_can_be_reactivated(self):
        cursor = FakeCursor(rowcount=1)
        conversation_id, target_id = uuid4(), uuid4()

        added = _add_or_reactivate_group_member(cursor, conversation_id, target_id)

        self.assertTrue(added)
        self.assertIn("joined_at=now()", cursor.query)
        self.assertIn("member_role='member'", cursor.query)

    def test_inactive_or_non_org_member_is_hidden(self):
        cursor = FakeCursor(one=None)

        with self.assertRaises(HTTPException) as error:
            _assert_group_owner(cursor, uuid4(), uuid4())

        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
