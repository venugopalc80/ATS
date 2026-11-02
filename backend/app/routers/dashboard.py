from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_permission, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# These rules are deliberately explicit and are surfaced in the response so the UI
# can explain why a vacancy needs attention rather than presenting an opaque score.
VACANCY_TARGET_DAYS = 30
VACANCY_MIN_APPLICATIONS = 3
OFFER_EXPIRY_WINDOW_DAYS = 3


def _organisation_zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Organisation timezone is misconfigured") from exc


def organisation_date_bounds_utc(timezone_name: str, local_date: date) -> tuple[datetime, datetime]:
    """Return UTC instants delimiting a local calendar date, including DST transitions."""
    zone = _organisation_zone(timezone_name)
    local_start = datetime.combine(local_date, time.min, tzinfo=zone)
    local_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def organisation_day_bounds_utc(timezone_name: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return UTC instants delimiting today in an organisation's IANA timezone."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_today = current.astimezone(_organisation_zone(timezone_name)).date()
    return organisation_date_bounds_utc(timezone_name, local_today)


@router.get("")
async def dashboard(
    organization_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "reports.read")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select timezone from public.organizations where id=%s",
                    [organization_id],
                )
                organisation_row = cursor.fetchone()
                if not organisation_row:
                    raise HTTPException(status_code=404, detail="Organisation not found")
                organisation_timezone = organisation_row.get("timezone") or "UTC"
                today_start_utc, tomorrow_start_utc = organisation_day_bounds_utc(organisation_timezone)
                local_today = datetime.now(timezone.utc).astimezone(_organisation_zone(organisation_timezone)).date()
                month_start_utc, _ = organisation_date_bounds_utc(
                    organisation_timezone, local_today.replace(day=1)
                )

                cursor.execute(
                    "select count(*)::int as total from public.jobs where organization_id=%s and status='open' and private.can_access_job(id, organization_id, %s)",
                    [organization_id, user_id],
                )
                open_jobs = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.candidates where organization_id=%s and status='active' and private.can_access_candidate(id, organization_id, %s)",
                    [organization_id, user_id],
                )
                active_candidates = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.interviews where organization_id=%s and status in ('scheduled','rescheduled') and scheduled_at >= %s and scheduled_at < %s and private.can_access_application(application_id, organization_id, %s)",
                    [organization_id, today_start_utc, tomorrow_start_utc, user_id],
                )
                interviews_today = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.placements where organization_id=%s and status='active' and private.can_access_application(application_id, organization_id, %s)",
                    [organization_id, user_id],
                )
                active_placements = cursor.fetchone()["total"]

                pipeline_params = [organization_id, user_id]
                pipeline_where = "organization_id=%s and private.can_access_application(id, organization_id, %s)"
                if date_from:
                    range_start_utc, _ = organisation_date_bounds_utc(organisation_timezone, date_from)
                    pipeline_where += " and created_at >= %s"
                    pipeline_params.append(range_start_utc)
                if date_to:
                    _, range_end_utc = organisation_date_bounds_utc(organisation_timezone, date_to)
                    pipeline_where += " and created_at < %s"
                    pipeline_params.append(range_end_utc)
                cursor.execute(
                    f"select status,count(*)::int as total from public.applications where {pipeline_where} group by status",
                    pipeline_params,
                )
                pipeline = {row["status"]: row["total"] for row in cursor.fetchall()}

                cursor.execute(
                    """select j.id,j.title,coalesce(c.name,'Direct client') as client,j.status,
                              count(a.id) filter (where private.can_access_application(a.id, a.organization_id, %s))::int as applicants,
                              (%s::date - (coalesce(j.opened_at,j.created_at) at time zone %s)::date)::int as days_open
                       from public.jobs j
                       left join public.clients c on c.id=j.client_id and c.organization_id=j.organization_id
                       left join public.applications a on a.job_id=j.id and a.organization_id=j.organization_id
                       where j.organization_id=%s and j.status in ('open','on_hold') and private.can_access_job(j.id, j.organization_id, %s)
                       group by j.id,j.title,c.name,j.status,j.created_at,j.opened_at
                       order by case when j.status='on_hold' then 0 else 1 end,
                                coalesce(j.opened_at,j.created_at) asc limit 10""",
                    [user_id, local_today, organisation_timezone, organization_id, user_id],
                )
                job_rows = list(cursor.fetchall())
                jobs = []
                vacancy_health = []
                for job in job_rows:
                    job = dict(job)
                    reasons = []
                    if job["status"] == "on_hold":
                        reasons.append("Role is on hold")
                    if job["status"] == "open" and job["days_open"] > VACANCY_TARGET_DAYS:
                        reasons.append(f"Open for more than {VACANCY_TARGET_DAYS} days")
                    if job["status"] == "open" and job["applicants"] < VACANCY_MIN_APPLICATIONS:
                        reasons.append(f"Fewer than {VACANCY_MIN_APPLICATIONS} applications")
                    job["health"] = "needs_attention" if reasons else "on_track"
                    job["health_reasons"] = reasons
                    jobs.append(job)
                    if reasons:
                        vacancy_health.append({
                            "id": str(job["id"]),
                            "title": job["title"],
                            "status": job["status"],
                            "applicants": job["applicants"],
                            "days_open": job["days_open"],
                            "reasons": reasons,
                        })

                # Reuse the interviews-today metric fetched above rather than
                # issuing the same organisation-scoped count query twice.
                interviews_today_count = interviews_today

                cursor.execute(
                    """select i.id,i.application_id,i.scheduled_at,i.status
                       from public.interviews i
                       where i.organization_id=%s
                         and i.status in ('scheduled','rescheduled')
                         and i.scheduled_at >= %s
                         and i.scheduled_at < %s
                         and private.can_access_application(i.application_id, i.organization_id, %s)
                       order by i.scheduled_at asc limit 10""",
                    [organization_id, today_start_utc, tomorrow_start_utc, user_id],
                )
                todays_interviews = list(cursor.fetchall())

                cursor.execute(
                    """select i.id,i.application_id,i.scheduled_at,i.status
                       from public.interviews i
                       where i.organization_id=%s and i.status='completed'
                         and (i.feedback is null or btrim(i.feedback)='')
                         and private.can_access_application(i.application_id, i.organization_id, %s)
                       order by i.scheduled_at desc limit 10""",
                    [organization_id, user_id],
                )
                pending_feedback = list(cursor.fetchall())

                cursor.execute(
                    """select o.id,o.application_id,o.title,o.expires_at,o.status
                       from public.offers o
                       where o.organization_id=%s and o.status='sent'
                         and private.can_access_application(o.application_id, o.organization_id, %s)
                         and o.expires_at >= now()
                         and o.expires_at < now() + (%s * interval '1 day')
                       order by o.expires_at asc limit 10""",
                    [organization_id, user_id, OFFER_EXPIRY_WINDOW_DAYS],
                )
                expiring_offers = list(cursor.fetchall())

                activity_where = """ae.organization_id=%s and (
                    (ae.entity_type='application' and private.can_access_application(ae.entity_id, ae.organization_id, %s))
                    or (ae.entity_type='job' and private.can_access_job(ae.entity_id, ae.organization_id, %s))
                    or (ae.entity_type='candidate' and private.can_access_candidate(ae.entity_id, ae.organization_id, %s))
                    or (ae.entity_type='client' and private.can_access_client(ae.entity_id, ae.organization_id, %s))
                    or (ae.entity_type='interview' and exists (
                        select 1 from public.interviews i where i.id=ae.entity_id
                          and private.can_access_application(i.application_id, i.organization_id, %s)))
                    or (ae.entity_type='offer' and exists (
                        select 1 from public.offers o where o.id=ae.entity_id
                          and private.can_access_application(o.application_id, o.organization_id, %s)))
                    or (ae.entity_type='placement' and exists (
                        select 1 from public.placements pl where pl.id=ae.entity_id
                          and private.can_access_application(pl.application_id, pl.organization_id, %s)))
                )"""
                activity_params = [organization_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id]
                if date_from:
                    activity_start_utc, _ = organisation_date_bounds_utc(organisation_timezone, date_from)
                    activity_where += " and ae.created_at >= %s"
                    activity_params.append(activity_start_utc)
                if date_to:
                    _, activity_end_utc = organisation_date_bounds_utc(organisation_timezone, date_to)
                    activity_where += " and ae.created_at < %s"
                    activity_params.append(activity_end_utc)
                cursor.execute(
                    f"""select ae.id,ae.action,ae.entity_type,ae.entity_id,ae.metadata,ae.created_at,
                               ae.actor_user_id,p.full_name as actor_name
                        from public.audit_events ae
                        left join public.profiles p on p.id=ae.actor_user_id
                        where {activity_where}
                        order by ae.created_at desc limit 10""",
                    activity_params,
                )
                activity = list(cursor.fetchall())

                cursor.execute(
                    """select count(*)::int as total from public.placements
                       where organization_id=%s and created_at >= %s and private.can_access_application(application_id, organization_id, %s)""",
                    [organization_id, month_start_utc, user_id],
                )
                placements_this_month = cursor.fetchone()["total"]

                cursor.execute(
                    """select count(*)::int as total from public.applications
                       where organization_id=%s and status in ('submitted','interview','offer')
                         and updated_at < now() - interval '3 days'
                         and private.can_access_application(id, organization_id, %s)""",
                    [organization_id, user_id],
                )
                awaiting_decision = cursor.fetchone()["total"]

        priorities = []
        for row in todays_interviews:
            priorities.append({
                "id": str(row["id"]),
                "type": "interview_today",
                "title": "Interview scheduled today",
                "description": f"Application {row['application_id']}",
                "href": f"/interviews?interview_id={row['id']}",
                "due_at": row["scheduled_at"],
            })
        for row in pending_feedback:
            priorities.append({
                "id": str(row["id"]),
                "type": "feedback_pending",
                "title": "Interview feedback outstanding",
                "description": f"Application {row['application_id']}",
                "href": f"/interviews?interview_id={row['id']}",
                "due_at": row["scheduled_at"],
            })
        for row in expiring_offers:
            priorities.append({
                "id": str(row["id"]),
                "type": "offer_expiring",
                "title": "Offer approaching expiry",
                "description": row["title"],
                "href": f"/offers?offer_id={row['id']}",
                "due_at": row["expires_at"],
            })
        if awaiting_decision:
            priorities.append({
                "id": "awaiting-decisions",
                "type": "awaiting_decision",
                "title": "Applications awaiting a decision",
                "description": f"{awaiting_decision} application(s) in submitted, interview or offer stage for more than 3 days",
                "href": "/submissions",
                "due_at": None,
            })
        for job in vacancy_health:
            priorities.append({
                "id": job["id"],
                "type": "vacancy_health",
                "title": "Vacancy needs attention",
                "description": f"{job['title']}: " + "; ".join(job["reasons"]),
                "href": f"/jobs?job_id={job['id']}",
                "due_at": None,
            })

        return {
            "timezone": organisation_timezone,
            "metrics": {
                "open_jobs": open_jobs,
                "active_candidates": active_candidates,
                "interviews_today": interviews_today_count,
                "placements_active": active_placements,
                "placements_this_month": placements_this_month,
            },
            "pipeline": pipeline,
            "jobs": jobs,
            "vacancy_health": vacancy_health,
            "priorities": priorities[:20],
            "activity": activity,
            "rules": {
                "vacancy_target_days": VACANCY_TARGET_DAYS,
                "vacancy_min_applications": VACANCY_MIN_APPLICATIONS,
                "offer_expiry_window_days": OFFER_EXPIRY_WINDOW_DAYS,
                "awaiting_decision_days": 3,
            },
            "date_range": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None,
            },
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Dashboard data is temporarily unavailable") from exc


def interviews_today_count(rows: list[dict]) -> int:
    return len(rows)
