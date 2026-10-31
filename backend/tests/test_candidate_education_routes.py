import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import candidates as candidates_router


ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
CANDIDATE = UUID("33333333-3333-4333-8333-333333333333")


class FakeCursor:
    def __init__(self):
        self.sql = ""
        self.params = []
        self.executed = []
        self.deleted = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params or []
        self.executed.append((self.sql, self.params))
        if self.sql.startswith("delete from public.candidate_education"):
            self.deleted = True

    def fetchone(self):
        if self.sql.startswith("select organization_id from public.candidates"):
            return {"organization_id": ORG}
        if "returning id, institution" in self.sql:
            return {
                "id": UUID("44444444-4444-4444-8444-444444444444"),
                "institution": "Coventry University",
                "qualification": "MSc",
                "field_of_study": "Computer Science",
                "start_year": 2024,
                "graduation_year": 2025,
                "raw_text": "MSc Computer Science, Coventry University",
            }
        return None

    def fetchall(self):
        return [{"institution": "Coventry University", "qualification": "MSc"}]


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class CandidateEducationEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_education_scopes_query_to_candidate_and_authorised_org(self):
        cursors = []

        @contextmanager
        def fake_connection():
            cursor = FakeCursor()
            cursors.append(cursor)
            yield FakeConnection(cursor)

        with patch.object(candidates_router, "get_connection", fake_connection), patch.object(
            candidates_router, "assert_org_member"
        ) as membership:
            result = await candidates_router.list_candidate_education(CANDIDATE, USER)

        membership.assert_called_once_with(USER, ORG)
        self.assertEqual(result, [{"institution": "Coventry University", "qualification": "MSc"}])
        query, params = cursors[-1].executed[-1]
        self.assertIn("where candidate_id=%s and organization_id=%s", query)
        self.assertEqual(params, [CANDIDATE, ORG])

    async def test_non_member_is_rejected_before_education_rows_are_read(self):
        cursor = FakeCursor()

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch.object(candidates_router, "get_connection", fake_connection), patch.object(
            candidates_router, "assert_org_member",
            side_effect=HTTPException(status_code=403, detail="forbidden"),
        ):
            with self.assertRaises(HTTPException) as error:
                await candidates_router.list_candidate_education(CANDIDATE, USER)

        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(len(cursor.executed), 1)
        self.assertTrue(cursor.executed[0][0].startswith("select organization_id from public.candidates"))

    async def test_empty_replacement_deletes_existing_education(self):
        cursors = []

        @contextmanager
        def fake_connection():
            cursor = FakeCursor()
            cursors.append(cursor)
            yield FakeConnection(cursor)

        with patch.object(candidates_router, "get_connection", fake_connection), patch.object(
            candidates_router, "assert_org_member"
        ):
            result = await candidates_router.replace_candidate_education(CANDIDATE, [], USER)

        self.assertEqual(result, [])
        self.assertTrue(cursors[-1].deleted)
        query, params = cursors[-1].executed[-1]
        self.assertIn("delete from public.candidate_education", query)
        self.assertEqual(params, [CANDIDATE, ORG])

    async def test_start_year_after_graduation_year_is_rejected_before_write(self):
        record = candidates_router.CandidateEducationInput(
            institution="Example University",
            qualification="BSc",
            start_year=2025,
            graduation_year=2023,
            raw_text="BSc, Example University",
        )

        @contextmanager
        def fake_connection():
            yield FakeConnection(FakeCursor())

        with patch.object(candidates_router, "get_connection", fake_connection), patch.object(
            candidates_router, "assert_org_member"
        ):
            with self.assertRaises(HTTPException) as error:
                await candidates_router.replace_candidate_education(CANDIDATE, [record], USER)

        self.assertEqual(error.exception.status_code, 422)

    async def test_valid_replacement_inserts_organisation_scoped_record(self):
        cursors = []
        record = candidates_router.CandidateEducationInput(
            institution="Coventry University",
            qualification="MSc",
            field_of_study="Computer Science",
            start_year=2024,
            graduation_year=2025,
            raw_text="MSc Computer Science, Coventry University",
        )

        @contextmanager
        def fake_connection():
            cursor = FakeCursor()
            cursors.append(cursor)
            yield FakeConnection(cursor)

        with patch.object(candidates_router, "get_connection", fake_connection), patch.object(
            candidates_router, "assert_org_member"
        ):
            result = await candidates_router.replace_candidate_education(CANDIDATE, [record], USER)

        self.assertEqual(len(result), 1)
        insert_query, params = cursors[-1].executed[-1]
        self.assertIn("insert into public.candidate_education", insert_query)
        self.assertEqual(params[:2], [ORG, CANDIDATE])


if __name__ == "__main__":
    unittest.main()
