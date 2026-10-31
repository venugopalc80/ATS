import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.db import DatabaseConnectionError
from app.routers.interviews import get_interview, update_interview
from app.schemas.interviews import InterviewUpdate


class InterviewRouteDatabaseFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_interview_returns_503_when_database_is_unavailable(self):
        with patch(
            "app.routers.interviews.service.get_interview",
            side_effect=DatabaseConnectionError("database unavailable"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await get_interview(uuid4(), uuid4())

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "Database operation failed")

    async def test_update_interview_returns_503_when_database_fails_after_lookup(self):
        organization_id = uuid4()
        interview_id = uuid4()
        user_id = uuid4()
        existing = {"id": interview_id, "organization_id": organization_id}
        with (
            patch(
                "app.routers.interviews.service.get_interview",
                return_value=existing,
            ),
            patch(
                "app.routers.interviews.service.update_interview",
                side_effect=DatabaseConnectionError("database unavailable"),
            ),
            patch("app.routers.interviews.assert_org_member"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await update_interview(
                    interview_id,
                    InterviewUpdate(notes="Updated interview notes"),
                    user_id,
                )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "Database operation failed")

    async def test_update_interview_returns_404_if_record_disappears_before_update(self):
        organization_id = uuid4()
        interview_id = uuid4()
        user_id = uuid4()
        existing = {"id": interview_id, "organization_id": organization_id}
        with (
            patch(
                "app.routers.interviews.service.get_interview",
                return_value=existing,
            ),
            patch(
                "app.routers.interviews.service.update_interview",
                return_value=None,
            ),
            patch("app.routers.interviews.assert_org_member"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await update_interview(
                    interview_id,
                    InterviewUpdate(notes="Updated interview notes"),
                    user_id,
                )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "Interview not found")


if __name__ == "__main__":
    unittest.main()
