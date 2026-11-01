from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def add_working_minutes(
    starts_at: datetime,
    minutes: int,
    *,
    timezone_name: str,
    business_days_only: bool = True,
    business_hours_start: time = time(9, 0),
    business_hours_end: time = time(17, 0),
    working_days: list[int] | tuple[int, ...] = (1, 2, 3, 4, 5),
) -> datetime:
    """Add elapsed minutes inside configured local working windows.

    ISO weekdays use Monday=1 through Sunday=7. The returned datetime is
    timezone-aware in UTC. Public holidays are intentionally not inferred;
    holiday calendars need an explicit organisation-level source.
    """
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("starts_at must be timezone-aware")
    if minutes < 0:
        raise ValueError("minutes cannot be negative")
    if business_hours_end <= business_hours_start:
        raise ValueError("business_hours_end must be later than business_hours_start")
    days = tuple(sorted(set(working_days)))
    if not days or any(day < 1 or day > 7 for day in days):
        raise ValueError("working_days must contain ISO weekdays 1 through 7")

    zone = ZoneInfo(timezone_name)
    remaining = timedelta(minutes=minutes)
    local_cursor = starts_at.astimezone(zone)
    if minutes == 0:
        return local_cursor.astimezone(timezone.utc)

    # The guard protects against pathological calendar/time-zone input.
    for _ in range(3660):
        current_date = local_cursor.date()
        eligible_day = (not business_days_only) or current_date.isoweekday() in days
        if eligible_day:
            opening = datetime.combine(current_date, business_hours_start, tzinfo=zone)
            closing = datetime.combine(current_date, business_hours_end, tzinfo=zone)
            cursor_utc = local_cursor.astimezone(timezone.utc)
            opening_utc = opening.astimezone(timezone.utc)
            closing_utc = closing.astimezone(timezone.utc)
            interval_start = max(cursor_utc, opening_utc)
            available = closing_utc - interval_start
            if available > timedelta(0):
                if remaining <= available:
                    return (interval_start + remaining).astimezone(timezone.utc)
                remaining -= available

        next_date = current_date + timedelta(days=1)
        local_cursor = datetime.combine(next_date, time.min, tzinfo=zone)

    raise ValueError("Unable to calculate SLA deadline within supported calendar horizon")
