import asyncio
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.last_query = ""
        self.last_params = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params or []
        self.calls.append((query, self.last_params))

    def fetchone(self):
        return {"total": 31}

    def fetchall(self):
        return [{"id": uuid4()}]


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.fake_cursor


class CandidateServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CandidateService()
        self.organization_id = uuid4()
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)

    def test_list_candidates_scopes_filters_and_paginates_in_database(self):
        with patch("app.services.candidate_service.get_connection", return_value=self.connection):
            rows, total = asyncio.run(
                self.service.list_candidates(
                    self.organization_id,
                    status="active",
                    search="Python",
                    country_code="gb",
                    page=2,
                    page_size=25,
                )
            )

        self.assertEqual(total, 31)
        self.assertEqual(len(rows), 1)
        self.assertIn("organization_id = %s", self.cursor.calls[0][0])
        self.assertIn("array_to_string(skills, ' ') ilike %s", self.cursor.calls[0][0])
        self.assertIn("limit %s offset %s", self.cursor.calls[1][0].lower())
        self.assertEqual(self.cursor.calls[1][1][-2:], [25, 25])
        self.assertEqual(self.cursor.calls[1][1][0], self.organization_id)

    def test_duplicate_lookup_normalises_email_and_phone_and_scopes_to_org(self):
        with patch("app.services.candidate_service.get_connection", return_value=self.connection):
            asyncio.run(
                self.service.find_duplicates(
                    self.organization_id,
                    email="  PERSON@Example.com ",
                    phone="+44 (0) 7700-900123",
                )
            )

        query, params = self.cursor.calls[0]
        self.assertIn("organization_id = %s", query)
        self.assertIn("lower(trim(email)) = %s", query)
        self.assertIn("regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g') = %s", query)
        self.assertEqual(params[0], self.organization_id)
        self.assertEqual(params[1], "person@example.com")
        self.assertEqual(params[2], "4407700900123")

    def test_candidate_lookup_requires_organisation_scope(self):
        candidate_id = uuid4()
        with patch("app.services.candidate_service.get_connection", return_value=self.connection):
            asyncio.run(self.service.get_candidate(candidate_id, self.organization_id))

        query, params = self.cursor.calls[0]
        self.assertIn("where id = %s and organization_id = %s", query)
        self.assertEqual(params, [candidate_id, self.organization_id])

    def test_candidate_response_does_not_expose_raw_cv_content_or_storage_path(self):
        self.assertNotIn("resume_text", CandidateOut.model_fields)
        self.assertNotIn("resume_path", CandidateOut.model_fields)

    def test_candidate_create_rejects_client_supplied_consent_metadata(self):
        for field, value in (
            ("consent_recorded_at", "2026-10-22T12:00:00Z"),
            ("consent_purpose", "recruitment"),
            ("retention_until", "2030-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                payload = {
                    "first_name": "Alex",
                    "organization_id": str(self.organization_id),
                    field: value,
                }
                with self.assertRaises(ValidationError):
                    CandidateCreate.model_validate(payload)

    def test_candidate_update_rejects_client_supplied_consent_metadata(self):
        for field, value in (
            ("consent_recorded_at", "2026-10-22T12:00:00Z"),
            ("consent_purpose", "recruitment"),
            ("retention_until", "2030-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    CandidateUpdate.model_validate({"first_name": "Alex", field: value})

    def test_candidate_update_rejects_null_for_required_fields(self):
        for payload in (
            {"first_name": None},
            {"status": None},
            {"skills": None},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    CandidateUpdate.model_validate(payload)

    def test_permanent_delete_is_blocked_when_candidate_has_applications(self):
        candidate_id = uuid4()
        self.cursor.rowcount = 0
        with patch("app.services.candidate_service.get_connection", return_value=self.connection):
            deleted = asyncio.run(self.service.delete_candidate(candidate_id, self.organization_id))

        query, params = self.cursor.calls[0]
        self.assertIn("not exists", query.lower())
        self.assertIn("public.applications", query)
        self.assertIn("application.candidate_id = candidate.id", query)
        self.assertEqual(params, [candidate_id, self.organization_id])
        self.assertFalse(deleted)


if __name__ == "__main__":
    unittest.main()
