import asyncio
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers import collaboration


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.fake_cursor


class CollaborationRouteScopeTests(unittest.TestCase):
    def test_contacts_route_checks_membership_and_scopes_query_to_requested_org(self):
        organization_id = uuid4()
        user_id = uuid4()
        cursor = FakeCursor(rows=[
            {"id": uuid4(), "full_name": "Recruiter One", "role": "recruiter"}
        ])
        connection = FakeConnection(cursor)

        with patch.object(collaboration, "assert_org_member") as membership_check, patch.object(
            collaboration, "get_connection", return_value=connection
        ):
            result = asyncio.run(
                collaboration.contacts(
                    organization_id=organization_id,
                    q="",
                    user_id=user_id,
                )
            )

        membership_check.assert_called_once_with(user_id, organization_id)
        self.assertIn("m.organization_id=%s", cursor.query)
        self.assertEqual(cursor.params, [organization_id, user_id, "", "%%"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["full_name"], "Recruiter One")

    def test_contacts_route_escapes_user_supplied_like_wildcards(self):
        organization_id = uuid4()
        user_id = uuid4()
        cursor = FakeCursor(rows=[])
        connection = FakeConnection(cursor)

        with patch.object(collaboration, "assert_org_member"), patch.object(
            collaboration, "get_connection", return_value=connection
        ):
            asyncio.run(
                collaboration.contacts(
                    organization_id=organization_id,
                    q="50%_off",
                    user_id=user_id,
                )
            )

        self.assertEqual(cursor.params, [organization_id, user_id, "50%_off", "%50\\%\\_off%"])


    def test_messages_route_rejects_non_member_before_reading_messages(self):
        conversation_id = uuid4()
        user_id = uuid4()

        class NonMemberCursor(FakeCursor):
            def fetchone(self):
                return None

        cursor = NonMemberCursor()
        connection = FakeConnection(cursor)

        with patch.object(collaboration, "get_connection", return_value=connection):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(
                    collaboration.list_messages(
                        conversation_id=conversation_id,
                        before=None,
                        limit=50,
                        user_id=user_id,
                    )
                )

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("cm.user_id=%s", cursor.query)
        self.assertEqual(cursor.params, [conversation_id, user_id])


    def test_messages_route_uses_composite_cursor_for_same_timestamp_messages(self):
        from datetime import datetime, timezone

        conversation_id, user_id, anchor_id = uuid4(), uuid4(), uuid4()
        joined_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        anchor_time = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
        message_id = uuid4()

        class Cursor(FakeCursor):
            def __init__(self):
                super().__init__(rows=[{
                    "id": message_id, "sender_user_id": user_id, "body": "Earlier message",
                    "created_at": anchor_time, "edited_at": None, "deleted_at": None,
                }])
                self.fetchone_rows = [{"joined_at": joined_at}, {"created_at": anchor_time}]

            def fetchone(self):
                return self.fetchone_rows.pop(0)

        cursor = Cursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            result = asyncio.run(collaboration.list_messages(
                conversation_id=conversation_id,
                before=None,
                before_message_id=anchor_id,
                limit=25,
                user_id=user_id,
            ))

        self.assertIn("(created_at,id) < (%s,%s)", cursor.query)
        self.assertEqual(cursor.params, [conversation_id, joined_at, anchor_time, anchor_id, 25])
        self.assertEqual(result[0]["id"], str(message_id))


    def test_add_members_response_only_includes_members_actually_added(self):
        organization_id = uuid4()
        conversation_id = uuid4()
        owner_id = uuid4()
        reactivated_id = uuid4()
        already_active_id = uuid4()

        class AddMembersCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.fetchone_rows = [
                    {"kind": "group", "member_role": "owner"},
                    {"organization_id": organization_id},
                ]
                self.fetchall_rows = [
                    {"user_id": reactivated_id},
                    {"user_id": already_active_id},
                ]
                self.reactivated_id = reactivated_id
                self.rowcount = 1

            def fetchone(self):
                return self.fetchone_rows.pop(0)

            def fetchall(self):
                if "select user_id from public.organization_members" in self.query:
                    return self.fetchall_rows
                return []

            def execute(self, query, params=None):
                super().execute(query, params)
                if "insert into public.conversation_members" in query:
                    self.rowcount = 1 if params[1] == self.reactivated_id else 0

        cursor = AddMembersCursor()
        connection = FakeConnection(cursor)

        with patch.object(collaboration, "get_connection", return_value=connection):
            result = asyncio.run(
                collaboration.add_group_members(
                    conversation_id=conversation_id,
                    payload=collaboration.GroupMembersAdd(
                        member_ids=[reactivated_id, already_active_id]
                    ),
                    user_id=owner_id,
                )
            )

        self.assertEqual(result, {"added": [str(reactivated_id)]})


    def test_owner_cannot_remove_themselves_through_member_removal_route(self):
        conversation_id, owner_id = uuid4(), uuid4()

        class OwnerCursor(FakeCursor):
            def fetchone(self):
                return {"kind": "group", "member_role": "owner"}

        cursor = OwnerCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(collaboration.remove_group_member(
                    conversation_id=conversation_id,
                    target_user_id=owner_id,
                    user_id=owner_id,
                ))

        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("select c.kind, cm.member_role", cursor.query)


    def test_remove_group_member_returns_not_found_for_inactive_member(self):
        conversation_id, owner_id, target_id = uuid4(), uuid4(), uuid4()

        class RemoveCursor(FakeCursor):
            rowcount = 0

            def fetchone(self):
                return {"kind": "group", "member_role": "owner"}

        cursor = RemoveCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(collaboration.remove_group_member(
                    conversation_id=conversation_id,
                    target_user_id=target_id,
                    user_id=owner_id,
                ))

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("left_at is null", cursor.query)


    def test_owner_leaving_transfers_ownership_to_oldest_active_member(self):
        conversation_id, owner_id, successor_id = uuid4(), uuid4(), uuid4()

        class LeaveCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.rows_to_fetch = [
                    {"id": conversation_id},
                    {"joined_at": "joined"},
                    {"kind": "group", "member_role": "owner"},
                    {"user_id": successor_id},
                ]
                self.queries = []

            def execute(self, query, params=None):
                super().execute(query, params)
                self.queries.append((query, params))

            def fetchone(self):
                return self.rows_to_fetch.pop(0)

        cursor = LeaveCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            result = asyncio.run(
                collaboration.leave_group(
                    conversation_id=conversation_id,
                    user_id=owner_id,
                )
            )

        self.assertEqual(result, {"left": True, "ownership_transferred": True})
        self.assertIn("for update", cursor.queries[0][0].lower())
        self.assertTrue(any("set member_role='owner'" in query for query, _ in cursor.queries))
        self.assertTrue(any("order by cm.joined_at asc limit 1" in query for query, _ in cursor.queries))
        self.assertTrue(any("'member_left'" in query for query, _ in cursor.queries))

    def test_last_owner_leaving_archives_group(self):
        conversation_id, owner_id = uuid4(), uuid4()

        class LeaveCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.rows_to_fetch = [
                    {"id": conversation_id},
                    {"joined_at": "joined"},
                    {"kind": "group", "member_role": "owner"},
                    None,
                ]
                self.queries = []

            def execute(self, query, params=None):
                super().execute(query, params)
                self.queries.append(query)

            def fetchone(self):
                return self.rows_to_fetch.pop(0)

        cursor = LeaveCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            result = asyncio.run(
                collaboration.leave_group(
                    conversation_id=conversation_id,
                    user_id=owner_id,
                )
            )

        self.assertEqual(result, {"left": True, "ownership_transferred": True})
        self.assertIn("for update", cursor.queries[0].lower())
        self.assertTrue(any("set archived_at=now()" in query for query in cursor.queries))

    def test_direct_conversation_cannot_be_left_through_group_endpoint(self):
        conversation_id, user_id = uuid4(), uuid4()

        class DirectCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.rows_to_fetch = [
                    {"id": conversation_id},
                    {"joined_at": "joined"},
                    {"kind": "direct", "member_role": "member"},
                ]
                self.queries = []

            def execute(self, query, params=None):
                super().execute(query, params)
                self.queries.append(query)

            def fetchone(self):
                return self.rows_to_fetch.pop(0)

        cursor = DirectCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(
                    collaboration.leave_group(
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )
                )

        self.assertEqual(error.exception.status_code, 422)
        self.assertFalse(any("set left_at=now()" in query for query in cursor.queries))


    def test_add_group_members_rejects_users_outside_conversation_organization(self):
        conversation_id, owner_id, foreign_user_id = uuid4(), uuid4(), uuid4()
        organization_id = uuid4()

        class ForeignMemberCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.fetchone_rows = [
                    {"kind": "group", "member_role": "owner"},
                    {"organization_id": organization_id},
                ]
                self.queries = []

            def execute(self, query, params=None):
                super().execute(query, params)
                self.queries.append(query)

            def fetchone(self):
                return self.fetchone_rows.pop(0)

            def fetchall(self):
                if "select user_id from public.organization_members" in self.query:
                    return []
                return []

        cursor = ForeignMemberCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(collaboration.add_group_members(
                    conversation_id=conversation_id,
                    payload=collaboration.GroupMembersAdd(member_ids=[foreign_user_id]),
                    user_id=owner_id,
                ))

        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("organization_members", cursor.query)
        self.assertFalse(any("insert into public.conversation_members" in query for query in cursor.queries))

    def test_former_organization_member_cannot_manage_group(self):
        conversation_id, former_owner_id = uuid4(), uuid4()

        class FormerOwnerCursor(FakeCursor):
            def fetchone(self):
                return None

        cursor = FormerOwnerCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(collaboration.update_group_title(
                    conversation_id=conversation_id,
                    payload=collaboration.GroupTitleUpdate(title="Renamed"),
                    user_id=former_owner_id,
                ))

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("organization_members", cursor.query)
        self.assertNotIn("update public.conversations", cursor.query)


    def test_mark_read_uses_wall_clock_cursor_after_membership_check(self):
        conversation_id, user_id = uuid4(), uuid4()

        class ReadCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.fetchone_rows = [{"joined_at": "joined"}]
                self.queries = []

            def execute(self, query, params=None):
                super().execute(query, params)
                self.queries.append(query)

            def fetchone(self):
                return self.fetchone_rows.pop(0)

        cursor = ReadCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            result = asyncio.run(collaboration.mark_read(
                conversation_id=conversation_id,
                user_id=user_id,
            ))

        self.assertEqual(result, {"ok": True})
        self.assertTrue(any("set last_read_at=greatest(coalesce(last_read_at,'-infinity'::timestamptz),clock_timestamp())" in query for query in cursor.queries))
        self.assertEqual(cursor.params, [conversation_id, user_id])


    def test_archived_group_owner_cannot_rename_group(self):
        conversation_id, owner_id = uuid4(), uuid4()

        class ArchivedGroupCursor(FakeCursor):
            def fetchone(self):
                return None

        cursor = ArchivedGroupCursor()
        with patch.object(collaboration, "get_connection", return_value=FakeConnection(cursor)):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(collaboration.update_group_title(
                    conversation_id=conversation_id,
                    payload=collaboration.GroupTitleUpdate(title="Should not update"),
                    user_id=owner_id,
                ))

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("c.archived_at is null", cursor.query)
        self.assertIn("for update of c", cursor.query.lower())
        self.assertNotIn("update public.conversations", cursor.query)


if __name__ == "__main__":
    unittest.main()
