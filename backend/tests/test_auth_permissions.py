import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.auth import require_permission


class PermissionCheckTests(unittest.TestCase):
    def setUp(self):
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection.__enter__.return_value = self.connection

    def run_check(self, rows, role="recruiter", permission="candidate.read_basic"):
        self.cursor.fetchone.side_effect = rows
        with patch("app.auth.get_connection") as get_connection:
            get_connection.return_value.__enter__.return_value = self.connection
            get_connection.return_value.__exit__.return_value = False
            require_permission(self.user_id, self.organization_id, permission)

    def test_owner_has_full_access_without_grant_lookup(self):
        self.run_check([{"role": "owner"}], permission="offer.salary.read")
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_admin_has_full_access_without_grant_lookup(self):
        self.run_check([{"role": "admin"}], permission="candidate.cv.download")
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_recruiter_with_active_grant_is_allowed(self):
        self.run_check([{"role": "recruiter"}, {"allowed": True}])
        self.assertEqual(self.cursor.execute.call_count, 2)

    def test_recruiter_without_grant_is_denied(self):
        with self.assertRaises(HTTPException) as error:
            self.run_check([{"role": "recruiter"}, {"allowed": False}])
        self.assertEqual(error.exception.status_code, 403)

    def test_non_member_is_denied_before_grant_lookup(self):
        with self.assertRaises(HTTPException) as error:
            self.run_check([None])
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_blank_permission_is_denied(self):
        with self.assertRaises(HTTPException) as error:
            require_permission(self.user_id, self.organization_id, " ")
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
