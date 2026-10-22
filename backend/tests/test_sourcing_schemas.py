from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from app.routers.sourcing import SavedSearchCreate, SearchCriteria, _escape_like, _search_rows

ORG_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeCursor:
    def __init__(self):
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return [{"id": "candidate-1"}]


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @contextmanager
    def cursor(self):
        yield self.cursor_instance


class SourcingSearchTests(TestCase):
    def test_search_terms_escape_like_wildcards(self):
        self.assertEqual(_escape_like("100%_safe!"), "100!%!_safe!!")

    def test_saved_search_rejects_unknown_criteria(self):
        with self.assertRaises(ValidationError):
            SearchCriteria.model_validate({"q": "python", "sql": "drop table candidates"})

    def test_saved_search_validates_record_type_and_criteria(self):
        payload = SavedSearchCreate.model_validate({
            "organization_id": str(ORG_ID),
            "name": "Python candidates",
            "record_type": "candidates",
            "criteria": {"q": "python", "skills": ["Python"]},
        })
        self.assertEqual(payload.record_type, "candidates")
        self.assertEqual(payload.criteria.skills, ["Python"])

    def test_search_is_tenant_scoped_and_uses_bound_search_values(self):
        connection = FakeConnection()

        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.routers.sourcing.get_connection", fake_connection):
            rows = _search_rows(
                ORG_ID,
                "candidates",
                SearchCriteria(q="100%_safe", skills=["Python"]),
                limit=10,
                offset=0,
            )

        self.assertEqual(rows, [{"id": "candidate-1"}])
        self.assertIn("base.organization_id = %s", connection.cursor_instance.query)
        self.assertNotIn("drop table", connection.cursor_instance.query.lower())
        self.assertEqual(str(ORG_ID), str(connection.cursor_instance.params[0]))
        self.assertIn("%100!%!_safe%", connection.cursor_instance.params)
        self.assertIn(["Python"], connection.cursor_instance.params)

    def test_application_search_joins_candidate_and_job_with_same_organisation(self):
        connection = FakeConnection()

        @contextmanager
        def fake_connection():
            yield connection

        with patch("app.routers.sourcing.get_connection", fake_connection):
            _search_rows(
                ORG_ID,
                "applications",
                SearchCriteria(q="developer", status="interview"),
                limit=10,
                offset=0,
            )

        sql = connection.cursor_instance.query
        self.assertIn("c.organization_id=base.organization_id", sql)
        self.assertIn("j.organization_id=base.organization_id", sql)
        self.assertIn("base.organization_id = %s", sql)
        self.assertIn("base.status = %s", sql)
