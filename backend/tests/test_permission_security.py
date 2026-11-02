"""Unit tests for organisation permission enforcement.

These tests isolate the permission resolver from Supabase/PostgreSQL. They verify
HTTP behaviour and the SQL scope/precedence contract; staging integration tests
are still required to validate the live database policies and joins.
"""
import unittest
import asyncio
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.auth import assert_org_permission, has_org_permission, has_resource_access, assert_resource_access
from app.routers.permissions import _assert_can_grant, _assert_team_manager
from app.services.interview_service import InterviewService
from app.services.offer_service import list_offers
from app.services.placement_service import list_placements


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, row):
        self.cursor_instance = FakeCursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_instance


class PermissionResolverTests(unittest.TestCase):
    def resolve(self, role, allowed, permission="jobs.read"):
        user_id, organization_id = uuid4(), uuid4()
        connection = FakeConnection({"role": role, "allowed": allowed})
        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.auth.get_connection", fake_connection):
            result = has_org_permission(user_id, organization_id, permission)

        sql = connection.cursor_instance.sql.lower()
        self.assertIn("m.organization_id = %s and m.user_id = %s", sql)
        self.assertIn("override.expires_at > now()", sql)
        self.assertEqual(connection.cursor_instance.params[-2:], [organization_id, user_id])
        return result

    def test_owner_has_access(self):
        self.assertTrue(self.resolve("owner", True, "ownership.transfer"))

    def test_admin_cannot_transfer_ownership(self):
        self.assertFalse(self.resolve("admin", False, "ownership.transfer"))

    def test_active_allow_override_is_respected(self):
        self.assertTrue(self.resolve("recruiter", True, "ai.configure"))

    def test_active_deny_override_is_respected(self):
        self.assertFalse(self.resolve("recruiter", False, "candidates.documents.read"))

    def test_role_default_is_respected_without_override(self):
        self.assertTrue(self.resolve("hiring_manager", True, "interviews.read"))
        self.assertFalse(self.resolve("viewer", False, "interviews.create"))

    def test_missing_membership_is_forbidden(self):
        user_id, organization_id = uuid4(), uuid4()
        connection = FakeConnection(None)
        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.auth.get_connection", fake_connection):
            with self.assertRaises(HTTPException) as caught:
                has_org_permission(user_id, organization_id, "jobs.read")
        self.assertEqual(caught.exception.status_code, 403)

    def test_assert_permission_returns_403_when_not_granted(self):
        user_id, organization_id = uuid4(), uuid4()
        connection = FakeConnection({"role": "viewer", "allowed": False})
        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.auth.get_connection", fake_connection):
            with self.assertRaises(HTTPException) as caught:
                assert_org_permission(user_id, organization_id, "jobs.delete")
        self.assertEqual(caught.exception.status_code, 403)



class PermissionGrantGuardTests(unittest.TestCase):
    def test_admin_cannot_grant_permission_they_do_not_hold(self):
        user_id, organization_id = uuid4(), uuid4()
        with patch("app.routers.permissions.get_org_role", return_value="admin"), \
             patch("app.routers.permissions.has_org_permission", return_value=False):
            with self.assertRaises(HTTPException) as caught:
                _assert_can_grant(user_id, organization_id, "billing.manage")
        self.assertEqual(caught.exception.status_code, 403)

    def test_admin_cannot_grant_ownership_transfer_even_if_permission_check_is_true(self):
        user_id, organization_id = uuid4(), uuid4()
        with patch("app.routers.permissions.get_org_role", return_value="admin"), \
             patch("app.routers.permissions.has_org_permission", return_value=True):
            with self.assertRaises(HTTPException) as caught:
                _assert_can_grant(user_id, organization_id, "ownership.transfer")
        self.assertEqual(caught.exception.status_code, 403)

    def test_admin_can_grant_a_permission_they_already_hold(self):
        user_id, organization_id = uuid4(), uuid4()
        with patch("app.routers.permissions.get_org_role", return_value="admin"), \
             patch("app.routers.permissions.has_org_permission", return_value=True):
            _assert_can_grant(user_id, organization_id, "candidates.read")

    def test_owner_can_grant_permissions(self):
        user_id, organization_id = uuid4(), uuid4()
        with patch("app.routers.permissions.get_org_role", return_value="owner"):
            _assert_can_grant(user_id, organization_id, "ownership.transfer")


class ResourceAccessResolverTests(unittest.TestCase):
    def test_resource_access_uses_fixed_query_and_user_context(self):
        user_id, organization_id, resource_id = uuid4(), uuid4(), uuid4()
        connection = FakeConnection({"allowed": True})

        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.auth.get_connection", fake_connection):
            self.assertTrue(has_resource_access(user_id, organization_id, "candidate", resource_id))

        self.assertIn("public.can_access_candidate", connection.cursor_instance.sql)
        self.assertEqual(connection.cursor_instance.params, [resource_id, organization_id, user_id])

    def test_inaccessible_resource_returns_same_not_found_response(self):
        user_id, organization_id, resource_id = uuid4(), uuid4(), uuid4()
        connection = FakeConnection({"allowed": False})

        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.auth.get_connection", fake_connection):
            with self.assertRaises(HTTPException) as caught:
                assert_resource_access(user_id, organization_id, "job", resource_id)

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "Job not found")

    def test_unknown_resource_type_is_rejected(self):
        with self.assertRaises(ValueError):
            has_resource_access(uuid4(), uuid4(), "invoice", uuid4())



class TeamManagementGuardTests(unittest.TestCase):
    def test_team_management_requires_team_manage_roles(self):
        user_id, organization_id = uuid4(), uuid4()
        with patch("app.routers.permissions.assert_org_permission") as permission_check:
            _assert_team_manager(user_id, organization_id)
        permission_check.assert_called_once_with(user_id, organization_id, "team.manage_roles")


class ResourceScopedListQueryTests(unittest.TestCase):
    def _connection(self):
        connection = FakeConnection(None)
        @contextmanager
        def fake_connection():
            yield connection
        return connection, fake_connection

    def test_interview_list_is_filtered_by_application_access(self):
        organization_id, user_id = uuid4(), uuid4()
        connection, fake_connection = self._connection()
        with patch("app.services.interview_service.get_connection", fake_connection):
            asyncio.run(InterviewService().list_interviews(organization_id, user_id))
        self.assertIn("public.can_access_application", connection.cursor_instance.sql)
        self.assertEqual(connection.cursor_instance.params, [organization_id, user_id])

    def test_offer_list_is_filtered_by_application_access(self):
        organization_id, user_id = uuid4(), uuid4()
        connection, fake_connection = self._connection()
        with patch("app.services.offer_service.get_connection", fake_connection):
            list_offers(organization_id, user_id)
        self.assertIn("public.can_access_application", connection.cursor_instance.sql)
        self.assertEqual(connection.cursor_instance.params, [organization_id, user_id])

    def test_placement_list_is_filtered_by_application_access(self):
        organization_id, user_id = uuid4(), uuid4()
        connection, fake_connection = self._connection()
        with patch("app.services.placement_service.get_connection", fake_connection):
            list_placements(organization_id, user_id)
        self.assertIn("public.can_access_application", connection.cursor_instance.sql)
        self.assertEqual(connection.cursor_instance.params, [organization_id, user_id])


class ApplicationAssignmentBoundaryTests(unittest.TestCase):
    def test_candidate_assignment_does_not_grant_all_application_access(self):
        from pathlib import Path
        migration = (
            Path(__file__).resolve().parents[2]
            / "supabase"
            / "migrations"
            / "20261102180000_resource_level_access_control_v2.sql"
        ).read_text()
        start = migration.index("create or replace function public.can_access_application")
        end = migration.index("$;", start)
        function_sql = migration[start:end]
        self.assertIn("public.application_access_assignments", function_sql)
        self.assertIn("public.can_access_job", function_sql)
        self.assertNotIn("public.can_access_candidate", function_sql)


if __name__ == "__main__":
    unittest.main()
