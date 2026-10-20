from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# These rules are deliberately explicit and are surfaced in the response so the UI
# can explain why a vacancy needs attention rather than presenting an opaque score.
VACANCY_TARGET_DAYS = 30
VACANCY_MIN_APPLICATIONS = 3
OFFER_EXPIRY_WINDOW_DAYS = 3


@router.get("")
async def dashboard(
    organization_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*)::int as total from public.jobs where organization_id=%s and status='open'",
                    [organization_id],
                )
                open_jobs = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.candidates where organization_id=%s and status='active'",
                    [organization_id],
                )
                active_candidates = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.interviews where organization_id=%s and status in ('scheduled','rescheduled') and scheduled_at >= date_trunc('day', now()) and scheduled_at < date_trunc('day', now()) + interval '1 day'",
                    [organization_id],
                )
                interviews_today = cursor.fetchone()["total"]

                cursor.execute(
                    "select count(*)::int as total from public.placements where organization_id=%s and status='active'",
                    [organization_id],
                )
                active_placements = cursor.fetchone()["total"]

                pipeline_params = [organization_id]
                pipeline_where = "organization_id=%s"
                if date_from:
                    pipeline_where += " and created_at >= %s"
                    pipeline_params.append(date_from)
                if date_to:
                    pipeline_where += " and created_at < (%s::date + interval '1 day')"
                    pipeline_params.append(date_to)
                cursor.execute(
                    f"select status,count(*)::int as total from public.applications where {pipeline_where} group by status",
                    pipeline_params,
                )
                pipeline = {row["status"]: row["total"] for row in cursor.fetchall()}

                cursor.execute(
                    """select j.id,j.title,coalesce(c.name,'Direct client') as client,j.status,
                              count(a.id)::int as applicants,
                              (current_date - coalesce(j.opened_at,j.created_at)::date)::int as days_open
                       from public.jobs j
                       left join public.clients c on c.id=j.client_id and c.organization_id=j.organization_id
                       left join public.applications a on a.job_id=j.id and a.organization_id=j.organization_id
                       where j.organization_id=%s and j.status in ('open','on_hold')
                       group by j.id,j.title,c.name,j.status,j.created_at,j.opened_at
                       order by j.created_at asc limit 10""",
                    [organization_id],
                )
                job_rows = list(cursor.fetchall())
                jobs = []
                vacancy_health = []
                for job in job_rows:
                    job = dict(job)
                    reasons = []
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
                         and i.scheduled_at >= date_trunc('day', now())
                         and i.scheduled_at < date_trunc('day', now()) + interval '1 day'
                       order by i.scheduled_at asc limit 10""",
                    [organization_id],
                )
                todays_interviews = list(cursor.fetchall())

                cursor.execute(
                    """select i.id,i.application_id,i.scheduled_at,i.status
                       from public.interviews i
                       where i.organization_id=%s and i.status='completed'
                         and (i.feedback is null or btrim(i.feedback)='')
                       order by i.scheduled_at desc limit 10""",
                    [organization_id],
                )
                pending_feedback = list(cursor.fetchall())

                cursor.execute(
                    """select o.id,o.application_id,o.title,o.expires_at,o.status
                       from public.offers o
                       where o.organization_id=%s and o.status='sent'
                         and o.expires_at >= now()
                         and o.expires_at < now() + (%s * interval '1 day')
                       order by o.expires_at asc limit 10""",
                    [organization_id, OFFER_EXPIRY_WINDOW_DAYS],
                )
                expiring_offers = list(cursor.fetchall())

                cursor.execute(
                    """select ae.id,ae.action,ae.entity_type,ae.entity_id,ae.metadata,ae.created_at,
                              ae.actor_user_id,p.full_name as actor_name
                       from public.audit_events ae
                       left join public.profiles p on p.id=ae.actor_user_id
                       where ae.organization_id=%s
                         and (%s::date is null or ae.created_at >= %s::date)
                         and (%s::date is null or ae.created_at < (%s::date + interval '1 day'))
                       order by ae.created_at desc limit 10""",
                    [organization_id, date_from, date_from, date_to, date_to],
                )
                activity = list(cursor.fetchall())

                cursor.execute(
                    """select count(*)::int as total from public.placements
                       where organization_id=%s and created_at >= date_trunc('month', now())""",
                    [organization_id],
                )
                placements_this_month = cursor.fetchone()["total"]

                cursor.execute(
                    """select count(*)::int as total from public.applications
                       where organization_id=%s and status in ('submitted','interview','offer')
                         and updated_at < now() - interval '3 days'""",
                    [organization_id],
                )
                awaiting_decision = cursor.fetchone()["total"]

                # Team workload is based only on explicitly assigned open vacancies.
                # Keep every join organisation-scoped to avoid cross-tenant aggregation.
                cursor.execute(
                    """select om.user_id,
                              coalesce(nullif(btrim(p.full_name), ''), nullif(btrim(p.email), ''), 'Team member') as name,
                              count(distinct j.id) filter (where j.status='open')::int as open_vacancies,
                              count(distinct a.id) filter (where a.status in ('new','screening','submitted','interview','offer'))::int as active_applications,
                              count(distinct a.id) filter (where a.status in ('submitted','interview','offer')
                                and a.updated_at < now() - interval '3 days')::int as overdue_decisions
                       from public.organization_members om
                       left join public.profiles p on p.id=om.user_id
                       left join public.jobs j on j.organization_id=om.organization_id
                         and j.recruiter_id=om.user_id and j.status in ('open','on_hold')
                       left join public.applications a on a.organization_id=om.organization_id and a.job_id=j.id
                       where om.organization_id=%s
                       group by om.user_id,p.full_name,p.email
                       order by count(distinct j.id) filter (where j.status='open') desc,
                                count(distinct a.id) filter (where a.status in ('new','screening','submitted','interview','offer')) desc
                       limit 10""",
                    [organization_id],
                )
                team_workload = list(cursor.fetchall())

                # Compare explicitly recorded required skills on open jobs with
                # skills recorded on active candidates. This is descriptive supply
                # and demand, not an automated hiring decision.
                cursor.execute(
                    """with demand as (
                         select lower(btrim(skill)) as skill,
                                min(btrim(skill)) as label,
                                count(distinct j.id)::int as open_roles
                         from public.jobs j
                         cross join lateral unnest(j.required_skills) as skill
                         where j.organization_id=%s and j.status='open' and btrim(skill)<>''
                         group by lower(btrim(skill))
                       ), supply as (
                         select lower(btrim(skill)) as skill,
                                count(distinct c.id)::int as active_candidates
                         from public.candidates c
                         cross join lateral unnest(c.skills) as skill
                         where c.organization_id=%s and c.status='active' and btrim(skill)<>''
                         group by lower(btrim(skill))
                       )
                       select d.skill,d.label,d.open_roles,coalesce(s.active_candidates,0)::int as active_candidates
                       from demand d left join supply s on s.skill=d.skill
                       order by d.open_roles desc, coalesce(s.active_candidates,0) asc, d.label asc
                       limit 8""",
                    [organization_id, organization_id],
                )
                talent_intelligence = list(cursor.fetchall())

        priorities = []
        for row in todays_interviews:
            priorities.append({
                "id": str(row["id"]),
                "type": "interview_today",
                "title": "Interview scheduled today",
                "description": f"Application {row['application_id']}",
                "href": f"/interviews/{row['id']}",
                "due_at": row["scheduled_at"],
            })
        for row in pending_feedback:
            priorities.append({
                "id": str(row["id"]),
                "type": "feedback_pending",
                "title": "Interview feedback outstanding",
                "description": f"Application {row['application_id']}",
                "href": f"/interviews/{row['id']}",
                "due_at": row["scheduled_at"],
            })
        for row in expiring_offers:
            priorities.append({
                "id": str(row["id"]),
                "type": "offer_expiring",
                "title": "Offer approaching expiry",
                "description": row["title"],
                "href": f"/offers/{row['id']}",
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
            "team_workload": [
                {
                    "user_id": str(row["user_id"]),
                    "name": row["name"],
                    "open_vacancies": row["open_vacancies"],
                    "active_applications": row["active_applications"],
                    "overdue_decisions": row["overdue_decisions"],
                }
                for row in team_workload
            ],
            "talent_intelligence": [
                {
                    "skill": row["label"],
                    "open_roles": row["open_roles"],
                    "active_candidates": row["active_candidates"],
                    "gap": max(row["open_roles"] - row["active_candidates"], 0),
                }
                for row in talent_intelligence
            ],
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
