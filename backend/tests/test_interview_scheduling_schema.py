import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.interviews import InterviewCreate, InterviewUpdate


class InterviewSchedulingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.base_payload = {
            "organization_id": uuid4(),
            "application_id": uuid4(),
            "scheduled_at": "2026-11-02T09:30:00+00:00",
        }

    def test_create_requires_timezone_aware_datetime(self):
        payload = {**self.base_payload, "scheduled_at": "2026-11-02T09:30:00"}
        with self.assertRaises(ValidationError):
            InterviewCreate(**payload)

    def test_create_accepts_explicit_utc_offset(self):
        interview = InterviewCreate(**self.base_payload)
        self.assertEqual(interview.scheduled_at.utcoffset(), timedelta(0))

    def test_create_cannot_start_in_completed_state(self):
        with self.assertRaises(ValidationError):
            InterviewCreate(**{**self.base_payload, "status": "completed"})

    def test_update_rejects_naive_reschedule_datetime(self):
        with self.assertRaises(ValidationError):
            InterviewUpdate(scheduled_at=datetime(2026, 11, 2, 9, 30))

    def test_update_accepts_timezone_aware_reschedule_datetime(self):
        updated = InterviewUpdate(scheduled_at=datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(updated.scheduled_at.utcoffset(), timedelta(0))

    def test_duration_is_bounded(self):
        with self.assertRaises(ValidationError):
            InterviewCreate(**{**self.base_payload, "duration_minutes": 600})


if __name__ == "__main__":
    unittest.main()
