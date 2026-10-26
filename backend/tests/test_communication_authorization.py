"""Route-level authorization regression tests for AQERITH communication features."""

import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import communications, notifications
from app.routers.notifications import PreferenceUpdate

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("33333333-3333-4333-8333-333333333333")
APPLICATION = UUID("22222222-2222-4222-8222-222222222222")


class CommunicationAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_threads_rejects_non_member_before_database_access(self):
        with patch.object(
            communications, "assert_org_member",
            side_effect=HTTPException(status_code=403, detail="forbidden"),
        ), patch.object(communications, "get_connection") as get_connection:
            with self.assertRaises(HTTPException) as raised:
                await communications.list_threads(
                    organization_id=ORG,
                    application_id=APPLICATION,
                    user_id=USER,
                )

        self.assertEqual(raised.exception.status_code, 403)
        get_connection.assert_not_called()

    async def test_essential_notification_opt_out_is_rejected_without_database_write(self):
        payload = PreferenceUpdate(
            organization_id=ORG,
            notification_type="security.session_expiring",
            channel="in_app",
            enabled=False,
        )
        with patch.object(notifications, "assert_org_member") as assert_member, patch.object(
            notifications, "get_connection"
        ) as get_connection:
            with self.assertRaises(HTTPException) as raised:
                await notifications.update_preference(payload=payload, user_id=USER)

        self.assertEqual(raised.exception.status_code, 422)
        assert_member.assert_called_once_with(USER, ORG)
        get_connection.assert_not_called()

    async def test_non_member_cannot_attempt_notification_preference_change(self):
        payload = PreferenceUpdate(
            organization_id=ORG,
            notification_type="interview_reminder",
            channel="email",
            enabled=False,
        )
        with patch.object(
            notifications, "assert_org_member",
            side_effect=HTTPException(status_code=403, detail="forbidden"),
        ), patch.object(notifications, "get_connection") as get_connection:
            with self.assertRaises(HTTPException) as raised:
                await notifications.update_preference(payload=payload, user_id=USER)

        self.assertEqual(raised.exception.status_code, 403)
        get_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
