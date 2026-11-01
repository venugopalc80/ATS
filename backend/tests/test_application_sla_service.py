import unittest
from datetime import datetime, time, timezone

from app.services.application_sla_service import add_working_minutes


class WorkingMinutesTests(unittest.TestCase):
    def test_adds_minutes_within_same_working_day(self):
        result = add_working_minutes(
            datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
            120,
            timezone_name="Europe/London",
        )
        self.assertEqual(result, datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc))

    def test_rolls_remaining_time_to_next_working_day(self):
        result = add_working_minutes(
            datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc),
            120,
            timezone_name="Europe/London",
        )
        self.assertEqual(result, datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc))

    def test_moves_weekend_start_to_monday(self):
        result = add_working_minutes(
            datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc),
            60,
            timezone_name="Europe/London",
        )
        self.assertEqual(result, datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc))

    def test_respects_configured_weekday_and_hours(self):
        result = add_working_minutes(
            datetime(2026, 11, 2, 16, 30, tzinfo=timezone.utc),
            60,
            timezone_name="Europe/London",
            business_hours_start=time(10, 0),
            business_hours_end=time(18, 0),
            working_days=[1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(result, datetime(2026, 11, 3, 10, 30, tzinfo=timezone.utc))

    def test_uses_local_timezone_across_dst_boundary(self):
        result = add_working_minutes(
            datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc),
            180,
            timezone_name="Europe/London",
        )
        self.assertEqual(result, datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc))

    def test_rejects_naive_start(self):
        with self.assertRaises(ValueError):
            add_working_minutes(
                datetime(2026, 11, 2, 10, 0),
                30,
                timezone_name="Europe/London",
            )

    def test_rejects_invalid_window(self):
        with self.assertRaises(ValueError):
            add_working_minutes(
                datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
                30,
                timezone_name="Europe/London",
                business_hours_start=time(17, 0),
                business_hours_end=time(9, 0),
            )


if __name__ == "__main__":
    unittest.main()
