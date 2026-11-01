import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers import candidate_portal


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.value


@contextmanager
def connection_for(cursor):
    yield Connection(cursor)


class TestCandidatePortalTenantBoundary:
    def test_profile_rejects_account_not_linked_in_requested_tenant(self):
        user_id, organization_id = uuid4(), uuid4()
        link_cursor = Cursor(row=None)
        user = SimpleNamespace(id=user_id)

        with patch.object(
            candidate_portal, "get_connection",
            side_effect=lambda: connection_for(link_cursor),
        ) as get_connection:
            try:
                asyncio.run(candidate_portal.get_candidate_portal_profile(
                    organization_id=organization_id, user=user
                ))
                assert False, "Expected an unlinked tenant to be rejected"
            except HTTPException as exc:
                assert exc.status_code == 404

        assert get_connection.call_count == 1
        assert link_cursor.params == [user_id, organization_id]

    def test_profile_query_uses_linked_candidate_and_requested_tenant(self):
        user_id, organization_id, candidate_id = uuid4(), uuid4(), uuid4()
        link_cursor = Cursor(row={"candidate_id": candidate_id})
        profile_cursor = Cursor(row={"email": "candidate@example.com"})
        cursors = iter([link_cursor, profile_cursor])

        def get_connection():
            return connection_for(next(cursors))

        with patch.object(candidate_portal, "get_connection", side_effect=get_connection):
            result = asyncio.run(candidate_portal.get_candidate_portal_profile(
                organization_id=organization_id, user=SimpleNamespace(id=user_id)
            ))

        assert result["profile"]["email"] == "candidate@example.com"
        assert "where id=%s and organization_id=%s" in profile_cursor.query.lower()
        assert profile_cursor.params == [candidate_id, organization_id]

    def test_application_list_is_scoped_to_linked_candidate_and_tenant(self):
        user_id, organization_id, candidate_id = uuid4(), uuid4(), uuid4()
        link_cursor = Cursor(row={"candidate_id": candidate_id})
        applications_cursor = Cursor(rows=[{"id": uuid4(), "status": "screening"}])
        cursors = iter([link_cursor, applications_cursor])

        def get_connection():
            return connection_for(next(cursors))

        with patch.object(candidate_portal, "get_connection", side_effect=get_connection):
            result = asyncio.run(candidate_portal.list_candidate_portal_applications(
                organization_id=organization_id, user=SimpleNamespace(id=user_id)
            ))

        query = applications_cursor.query.lower()
        assert "where a.organization_id=%s and a.candidate_id=%s" in query
        assert applications_cursor.params == [organization_id, candidate_id]
        assert len(result["applications"]) == 1

    def test_application_detail_requires_application_candidate_and_tenant_match(self):
        user_id, organization_id, candidate_id, application_id = [uuid4() for _ in range(4)]
        link_cursor = Cursor(row={"candidate_id": candidate_id})
        application_cursor = Cursor(row=None)
        cursors = iter([link_cursor, application_cursor])

        def get_connection():
            return connection_for(next(cursors))

        with patch.object(candidate_portal, "get_connection", side_effect=get_connection):
            try:
                asyncio.run(candidate_portal.get_candidate_portal_application(
                    application_id=application_id,
                    organization_id=organization_id,
                    user=SimpleNamespace(id=user_id),
                ))
                assert False, "Expected an application outside the candidate scope to be hidden"
            except HTTPException as exc:
                assert exc.status_code == 404

        query = application_cursor.query.lower()
        assert "where a.id=%s and a.organization_id=%s and a.candidate_id=%s" in query
        assert application_cursor.params == [application_id, organization_id, candidate_id]

    def test_document_list_is_scoped_and_excludes_deleted_documents(self):
        user_id, organization_id, candidate_id = uuid4(), uuid4(), uuid4()
        link_cursor = Cursor(row={"candidate_id": candidate_id})
        documents_cursor = Cursor(rows=[])
        cursors = iter([link_cursor, documents_cursor])

        def get_connection():
            return connection_for(next(cursors))

        with patch.object(candidate_portal, "get_connection", side_effect=get_connection):
            result = asyncio.run(candidate_portal.list_candidate_portal_documents(
                organization_id=organization_id, user=SimpleNamespace(id=user_id)
            ))

        query = documents_cursor.query.lower()
        assert "d.organization_id=%s and d.candidate_id=%s" in query
        assert "d.deleted_at is null" in query
        assert documents_cursor.params == [organization_id, candidate_id]
        assert result == {"documents": []}
