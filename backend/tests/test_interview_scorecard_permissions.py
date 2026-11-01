import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services import interview_scorecard_service as service


class InterviewScorecardPermissionTests(unittest.TestCase):
    def setUp(self):
        self.organization_id = uuid4()
        self.interview_id = uuid4()
        self.assigned_interviewer = uuid4()
        self.other_interviewer = uuid4()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connection.cursor.return_value.__exit__.return_value = False

    def patched_connection(self):
        manager = MagicMock()
        manager.__enter__.return_value = self.connection
        manager.__exit__.return_value = False
        return manager

    @patch("app.services.interview_scorecard_service.get_connection")
    def test_unassigned_user_cannot_save_feedback(self, get_connection):
        get_connection.return_value = self.patched_connection()
        self.cursor.fetchone.return_value = {
            "id": self.interview_id,
            "application_id": uuid4(),
            "interviewer_ids": [str(self.assigned_interviewer)],
            "interview_status": "completed",
            "job_id": uuid4(),
        }

        with self.assertRaises(PermissionError):
            service.save_feedback(
                self.organization_id,
                self.interview_id,
                self.other_interviewer,
                MagicMock(),
                submit=False,
            )

    @patch("app.services.interview_scorecard_service.get_connection")
    def test_assigned_interviewer_cannot_review_before_own_submission(self, get_connection):
        get_connection.return_value = self.patched_connection()
        self.cursor.fetchone.side_effect = [
            {"interviewer_ids": [str(self.assigned_interviewer), str(self.other_interviewer)]},
            None,
        ]

        with self.assertRaisesRegex(PermissionError, "Submit your own scorecard"):
            service.review_feedback(
                self.organization_id,
                self.interview_id,
                self.assigned_interviewer,
                can_review_early=True,
            )

    @patch("app.services.interview_scorecard_service.get_connection")
    def test_unassigned_non_admin_cannot_review(self, get_connection):
        get_connection.return_value = self.patched_connection()
        self.cursor.fetchone.return_value = {"interviewer_ids": [str(self.assigned_interviewer)]}

        with self.assertRaisesRegex(PermissionError, "Only assigned interviewers"):
            service.review_feedback(
                self.organization_id,
                self.interview_id,
                self.other_interviewer,
                can_review_early=False,
            )


if __name__ == "__main__":
    unittest.main()
