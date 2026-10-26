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


if __name__ == "__main__":
    unittest.main()
