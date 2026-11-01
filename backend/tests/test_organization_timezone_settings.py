import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import me


ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")


class FakeCursor:
    def __init__(self):
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params

    def fetchone(self):
        return {"id": ORG, "timezone": "Asia/Kolkata"}


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


class OrganizationTimezoneSettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_timezone_defaults_to_utc_for_older_clients(self):
        payload = me.OrganizationCreate(name="Example Agency", country_code="GB")
        self.assertEqual(payload.timezone, "UTC")

    def test_timezone_accepts_valid_iana_names(self):
        self.assertEqual(
            me.OrganizationSettingsUpdate(timezone="Europe/London").timezone,
            "Europe/London",
        )

    def test_timezone_rejects_invalid_iana_names(self):
        with self.assertRaises(ValidationError):
            me.OrganizationSettingsUpdate(timezone="Not/A_Real_Zone")

    async def test_admin_can_update_only_the_selected_organisation(self):
        cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection

        with patch.object(me, "assert_org_admin") as admin_check, patch.object(
            me, "get_connection", fake_connection
        ):
            result = await me.update_organization_settings(
                organization_id=ORG,
                payload=me.OrganizationSettingsUpdate(timezone="Asia/Kolkata"),
                user_id=USER,
            )

        admin_check.assert_called_once_with(USER, ORG)
        self.assertEqual(result["organization"]["timezone"], "Asia/Kolkata")
        self.assertIn("where id = %s", cursor.sql)
        self.assertEqual(cursor.params, ["Asia/Kolkata", ORG])

    async def test_non_admin_is_rejected_before_database_update(self):
        with patch.object(
            me, "assert_org_admin", side_effect=HTTPException(status_code=403, detail="Admin access required")
        ) as admin_check, patch.object(me, "get_connection") as connection:
            with self.assertRaises(HTTPException) as error:
                await me.update_organization_settings(
                    organization_id=ORG,
                    payload=me.OrganizationSettingsUpdate(timezone="Europe/London"),
                    user_id=USER,
                )

        self.assertEqual(error.exception.status_code, 403)
        admin_check.assert_called_once_with(USER, ORG)
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
