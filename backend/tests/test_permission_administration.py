import asyncio
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers.permissions import (
    PermissionGrantCreate,
    PermissionRevoke,
    grant_member_permission,
    revoke_member_permission,
)


class PermissionAdministrationTests(unittest.TestCase):
    def setUp(self):
        self.organization_id = uuid4()
        self.admin_id = uuid4()
        self.member_id = uuid4()
        self.grant_id = uuid4()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection.__enter__.return_value = self.connection

    def database(self, rows):
        self.cursor.fetchone.side_effect = rows
        manager = MagicMock()
        manager.__enter__.return_value = self.connection
        manager.__exit__.return_value = False
        return manager

    def test_admin_can_grant_known_permission_and_audit_it(self):
        grant = {
            "id": self.grant_id,
            "organization_id": self.organization_id,
            "user_id": self.member_id,
            "permission_key": "candidate.read_basic",
        }
        with patch("app.routers.permissions.assert_org_admin"), patch(
            "app.routers.permissions.get_connection",
            return_value=self.database([{"member": 1}, {"permission": 1}, grant]),
        ):
            result = asyncio.run(grant_member_permission(
                self.organization_id,
                self.member_id,
                PermissionGrantCreate(permission_key="candidate.read_basic"),
                self.admin_id,
            ))
        self.assertEqual(result, grant)
        self.assertEqual(self.cursor.execute.call_count, 4)

    def test_duplicate_active_grant_returns_conflict(self):
        with patch("app.routers.permissions.assert_org_admin"), patch(
            "app.routers.permissions.get_connection",
            return_value=self.database([{"member": 1}, {"permission": 1}, None]),
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(grant_member_permission(
                    self.organization_id,
                    self.member_id,
                    PermissionGrantCreate(permission_key="candidate.read_basic"),
                    self.admin_id,
                ))
        self.assertEqual(error.exception.status_code, 409)

    def test_revoke_records_actor_and_audit_event(self):
        revoked = {
            "id": self.grant_id,
            "organization_id": self.organization_id,
            "user_id": self.member_id,
            "permission_key": "candidate.read_basic",
        }
        with patch("app.routers.permissions.assert_org_admin"), patch(
            "app.routers.permissions.get_connection",
            return_value=self.database([revoked]),
        ):
            result = asyncio.run(revoke_member_permission(
                self.organization_id,
                self.member_id,
                "candidate.read_basic",
                PermissionRevoke(reason="Role change"),
                self.admin_id,
            ))
        self.assertEqual(result, revoked)
        self.assertEqual(self.cursor.execute.call_count, 2)

    def test_missing_active_grant_returns_not_found(self):
        with patch("app.routers.permissions.assert_org_admin"), patch(
            "app.routers.permissions.get_connection",
            return_value=self.database([None]),
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(revoke_member_permission(
                    self.organization_id,
                    self.member_id,
                    "candidate.read_basic",
                    PermissionRevoke(),
                    self.admin_id,
                ))
        self.assertEqual(error.exception.status_code, 404)

    def test_non_admin_cannot_grant_permission(self):
        denied = HTTPException(status_code=403, detail="Admin access required")
        with patch("app.routers.permissions.assert_org_admin", side_effect=denied), patch(
            "app.routers.permissions.get_connection"
        ) as get_connection:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(grant_member_permission(
                    self.organization_id,
                    self.member_id,
                    PermissionGrantCreate(permission_key="candidate.read_basic"),
                    self.member_id,
                ))
        self.assertEqual(error.exception.status_code, 403)
        get_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
