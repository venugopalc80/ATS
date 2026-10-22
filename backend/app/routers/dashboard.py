from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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

                cursor.execute(
                    """select t.id,t.title,t.description,t.task_type,t.candidate_id,t.job_id,t.assigned_to,t.due_at,t.status
                       from public.recruiter_tasks t
                       where t.organization_id=%s and t.status='open'
                         and (t.assigned_to is null or t.assigned_to=%s)
                       order by t.due_at asc limit 20""",
                    [organization_id, user_id],
                )
                recruiter_tasks = list(cursor.fetchall())

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

        for row in recruiter_tasks:
            linked_href = f"/candidates/{row['candidate_id']}" if row["candidate_id"] else (f"/jobs?job_id={row['job_id']}" if row["job_id"] else "/dashboard#priorities")
            due_at = row["due_at"]
            description = row["description"] or ("Candidate follow-up" if row["task_type"] == "candidate_follow_up" else "Recruiter task")
            if due_at and due_at < datetime.now(timezone.utc):
                description += " · Overdue"
            priorities.append({
                "id": str(row["id"]),
                "type": "candidate_follow_up" if row["task_type"] == "candidate_follow_up" else "recruiter_task",
                "title": row["title"],
                "description": description,
                "href": linked_href,
                "due_at": due_at,
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


class RecruiterTaskCreate(BaseModel):
    organization_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    task_type: str = Field(default="task", pattern="^(task|candidate_follow_up|vacancy_follow_up)$")
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None
    due_at: datetime


@router.get("/tasks")
async def list_recruiter_tasks(organization_id: UUID, status: str = Query(default="open", pattern="^(open|completed|cancelled|all)$"), user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                where_status = "" if status == "all" else " and status=%s"
                params = [organization_id] if status == "all" else [organization_id, status]
                cursor.execute(
                    "select id,organization_id,title,description,task_type,candidate_id,job_id,assigned_to,due_at,status,created_by,completed_by,completed_at,created_at,updated_at from public.recruiter_tasks where organization_id=%s" + where_status + " order by due_at asc limit 100",
                    params,
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Task data is temporarily unavailable") from exc


@router.post("/tasks", status_code=201)
async def create_recruiter_task(payload: RecruiterTaskCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    if payload.task_type != "task" and not (payload.candidate_id or payload.job_id):
        raise HTTPException(status_code=422, detail="Follow-up tasks must link to a candidate or vacancy")
    if payload.candidate_id and payload.job_id:
        raise HTTPException(status_code=422, detail="Link a task to either a candidate or a vacancy, not both")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if payload.candidate_id:
                    cursor.execute("select 1 from public.candidates where id=%s and organization_id=%s", [payload.candidate_id, payload.organization_id])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Candidate not found in this organisation")
                if payload.job_id:
                    cursor.execute("select 1 from public.jobs where id=%s and organization_id=%s", [payload.job_id, payload.organization_id])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Vacancy not found in this organisation")
                if payload.assigned_to:
                    cursor.execute("select 1 from public.organization_members where organization_id=%s and user_id=%s", [payload.organization_id, payload.assigned_to])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Assignee must belong to this organisation")
                cursor.execute(
                    """insert into public.recruiter_tasks (organization_id,title,description,task_type,candidate_id,job_id,assigned_to,due_at,created_by)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       returning id,organization_id,title,description,task_type,candidate_id,job_id,assigned_to,due_at,status,created_by,created_at,updated_at""",
                    [payload.organization_id, payload.title.strip(), payload.description, payload.task_type, payload.candidate_id, payload.job_id, payload.assigned_to, payload.due_at, user_id],
                )
                return cursor.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Task data is temporarily unavailable") from exc


@router.post("/tasks/{task_id}/complete")
async def complete_recruiter_task(task_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """update public.recruiter_tasks set status='completed',completed_by=%s,completed_at=now(),updated_at=now()
                       where id=%s and organization_id=%s and status='open'
                       returning id,status,completed_by,completed_at,updated_at""",
                    [user_id, task_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Open task not found in this organisation")
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Task data is temporarily unavailable") from exc
