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


class ApplicationSLADueService:
    """Persists calculated initial-review and first-action deadlines."""

    TARGETS = {
        "initial_review": "initial_review_minutes",
        "first_recruiter_action": "first_recruiter_action_minutes",
    }

    async def recalculate_initial_deadlines(
        self, application_id, organization_id
    ) -> list[dict]:
        from app.db import get_connection

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select created_at from public.applications "
                    "where id=%s and organization_id=%s",
                    [application_id, organization_id],
                )
                application = cursor.fetchone()
                if application is None:
                    return []
                cursor.execute(
                    "select initial_review_minutes, first_recruiter_action_minutes, "
                    "timezone, business_days_only, business_hours_start, "
                    "business_hours_end, working_days, enabled "
                    "from public.application_sla_policies where organization_id=%s",
                    [organization_id],
                )
                policy = cursor.fetchone()
                if policy is None or not policy["enabled"]:
                    return []

                created_at = application["created_at"]
                results = []
                for milestone, field in self.TARGETS.items():
                    due_at = add_working_minutes(
                        created_at,
                        policy[field],
                        timezone_name=policy["timezone"],
                        business_days_only=policy["business_days_only"],
                        business_hours_start=policy["business_hours_start"],
                        business_hours_end=policy["business_hours_end"],
                        working_days=policy["working_days"],
                    )
                    cursor.execute(
                        "insert into public.application_sla_deadlines "
                        "(organization_id, application_id, milestone, starts_at, due_at, status, "
                        "last_calculated_at, updated_at) "
                        "values (%s,%s,%s,%s,%s,case when %s < now() then 'overdue' else 'pending' end,now(),now()) "
                        "on conflict (application_id,milestone) do update set "
                        "starts_at=excluded.starts_at, due_at=excluded.due_at, "
                        "status=case when application_sla_deadlines.status='completed' "
                        "then 'completed' when excluded.due_at < now() then 'overdue' "
                        "else 'pending' end, last_calculated_at=now(), updated_at=now() "
                        "returning id, organization_id, application_id, milestone, starts_at, "
                        "due_at, status, completed_at, last_calculated_at, created_at, updated_at",
                        [organization_id, application_id, milestone, created_at, due_at, due_at],
                    )
                    results.append(cursor.fetchone())
                return results

    async def list_deadlines(self, application_id, organization_id) -> list[dict]:
        from app.db import get_connection

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id, organization_id, application_id, milestone, starts_at, due_at, "
                    "case when status in ('pending','overdue') and due_at < now() "
                    "then 'overdue' else status end as status, completed_at, "
                    "last_calculated_at, created_at, updated_at "
                    "from public.application_sla_deadlines "
                    "where application_id=%s and organization_id=%s "
                    "order by due_at, milestone",
                    [application_id, organization_id],
                )
                return list(cursor.fetchall())
