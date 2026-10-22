from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _validate_dates(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")


def _application_scope(organization_id: UUID, date_from: date | None, date_to: date | None,
                       job_id: UUID | None, recruiter_id: UUID | None) -> tuple[str, list]:
    clauses = ["a.organization_id = %s"]
    params = [organization_id]
    if date_from:
        clauses.append("a.created_at >= %s::date")
        params.append(date_from)
    if date_to:
        clauses.append("a.created_at < (%s::date + interval '1 day')")
        params.append(date_to)
    if job_id:
        clauses.append("a.job_id = %s")
        params.append(job_id)
    if recruiter_id:
        clauses.append("j.recruiter_id = %s")
        params.append(recruiter_id)
    return " and ".join(clauses), params


@router.get("/kpis")
async def analytics_kpis(
    organization_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Return a first, auditable KPI slice. Date filters on application measures use application creation date."""
    assert_org_member(user_id, organization_id)
    _validate_dates(date_from, date_to)
    app_where, app_params = _application_scope(
        organization_id, date_from, date_to, job_id, recruiter_id
    )

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select count(*)::int as applications,
                               count(*) filter (where a.status in ('rejected','withdrawn'))::int as closed_unsuccessfully,
                               count(*) filter (where a.status not in ('rejected','withdrawn','hired'))::int as active_applications
                        from public.applications a
                        join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                        where {app_where}""",
                    app_params,
                )
                application_row = cursor.fetchone()

                offer_where = ["o.organization_id = %s", "o.status in ('accepted','rejected')",
                               "a.organization_id = o.organization_id", "j.organization_id = a.organization_id"]
                offer_params = [organization_id]
                if date_from:
                    offer_where.append("o.responded_at >= %s::date")
                    offer_params.append(date_from)
                if date_to:
                    offer_where.append("o.responded_at < (%s::date + interval '1 day')")
                    offer_params.append(date_to)
                if job_id:
                    offer_where.append("a.job_id = %s")
                    offer_params.append(job_id)
                if recruiter_id:
                    offer_where.append("j.recruiter_id = %s")
                    offer_params.append(recruiter_id)
                cursor.execute(
                    f"""select count(*)::int as decided_offers,
                               count(*) filter (where o.status='accepted')::int as accepted_offers
                        from public.offers o
                        join public.applications a on a.id=o.application_id
                        join public.jobs j on j.id=a.job_id
                        where {' and '.join(offer_where)}""",
                    offer_params,
                )
                offer_row = cursor.fetchone()

                cursor.execute(
                    f"""select percentile_cont(0.5) within group (
                                  order by extract(epoch from (o.accepted_at - a.created_at)) / 86400.0
                               ) as median_days,
                               count(distinct a.id)::int as complete_records
                        from public.applications a
                        join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                        join lateral (
                            select min(off.responded_at) as accepted_at
                            from public.offers off
                            where off.application_id=a.id
                              and off.organization_id=a.organization_id
                              and off.status='accepted'
                              and off.responded_at is not null
                        ) o on o.accepted_at is not null
                        where {app_where}
                          and o.accepted_at >= a.created_at""",
                    app_params,
                )
                hire_row = cursor.fetchone()

                cursor.execute(
                    """select count(*)::int as open_vacancies
                       from public.jobs j
                       where j.organization_id=%s and j.status='open'
                         and (%s::uuid is null or j.id=%s::uuid)
                         and (%s::uuid is null or j.recruiter_id=%s::uuid)""",
                    [organization_id, job_id, job_id, recruiter_id, recruiter_id],
                )
                vacancy_row = cursor.fetchone()

        applications = application_row["applications"]
        decided_offers = offer_row["decided_offers"]
        accepted_offers = offer_row["accepted_offers"]
        complete_records = hire_row["complete_records"]
        return {
            "definitions_version": "1.0",
            "filters": {
                "organization_id": str(organization_id),
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "job_id": str(job_id) if job_id else None,
                "recruiter_id": str(recruiter_id) if recruiter_id else None,
                "application_cohort": "application_created_at",
                "offer_cohort": "offer_responded_at",
            },
            "metrics": {
                "applications": {"value": applications, "status": "available" if applications else "empty_cohort"},
                "active_applications": {"value": application_row["active_applications"], "status": "available" if applications else "empty_cohort"},
                "closed_unsuccessfully": {"value": application_row["closed_unsuccessfully"], "status": "available" if applications else "empty_cohort"},
                "offer_acceptance_rate": {
                    "value": accepted_offers / decided_offers if decided_offers else None,
                    "numerator": accepted_offers,
                    "denominator": decided_offers,
                    "status": "available" if decided_offers else "insufficient_decided_offers",
                },
                "median_time_to_hire_days": {
                    "value": float(hire_row["median_days"]) if hire_row["median_days"] is not None else None,
                    "complete_records": complete_records,
                    "status": "available" if complete_records else "insufficient_complete_records",
                    "definition": "Median calendar days from application creation to accepted offer response",
                },
                "open_vacancies": {"value": vacancy_row["open_vacancies"], "status": "available"},
            },
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc


@router.get("/funnel")
async def analytics_funnel(
    organization_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Count distinct applications entering each stage; repeated visits are reported separately."""
    assert_org_member(user_id, organization_id)
    _validate_dates(date_from, date_to)
    clauses = ["h.organization_id=%s", "a.organization_id=h.organization_id",
               "j.organization_id=a.organization_id"]
    params = [organization_id]
    if date_from:
        clauses.append("h.created_at >= %s::date")
        params.append(date_from)
    if date_to:
        clauses.append("h.created_at < (%s::date + interval '1 day')")
        params.append(date_to)
    if job_id:
        clauses.append("a.job_id=%s")
        params.append(job_id)
    if recruiter_id:
        clauses.append("j.recruiter_id=%s")
        params.append(recruiter_id)
    where = " and ".join(clauses)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select h.new_stage as stage,
                               count(*)::int as stage_visits,
                               count(distinct h.application_id)::int as distinct_applications
                        from public.application_stage_history h
                        join public.applications a on a.id=h.application_id
                        join public.jobs j on j.id=a.job_id
                        where {where}
                        group by h.new_stage
                        order by min(h.created_at), h.new_stage""",
                    params,
                )
                stages = [dict(row) for row in cursor.fetchall()]
                duration_clauses = [
                    "ei.organization_id=%s",
                    "a.organization_id=ei.organization_id",
                    "j.organization_id=a.organization_id",
                    "ei.exited_at is not null",
                    "ei.exited_at >= ei.entered_at",
                ]
                duration_params = [organization_id]
                if date_from:
                    duration_clauses.append("ei.entered_at >= %s::date")
                    duration_params.append(date_from)
                if date_to:
                    duration_clauses.append("ei.entered_at < (%s::date + interval '1 day')")
                    duration_params.append(date_to)
                if job_id:
                    duration_clauses.append("a.job_id=%s")
                    duration_params.append(job_id)
                if recruiter_id:
                    duration_clauses.append("j.recruiter_id=%s")
                    duration_params.append(recruiter_id)
                cursor.execute(
                    f"""with event_intervals as (
                            select h.organization_id, h.application_id, h.new_stage,
                                   h.created_at as entered_at,
                                   lead(h.created_at) over (
                                       partition by h.organization_id, h.application_id
                                       order by h.created_at, h.id
                                   ) as exited_at
                            from public.application_stage_history h
                            where h.organization_id=%s
                        )
                        select ei.new_stage as stage,
                               count(*)::int as completed_intervals,
                               percentile_cont(0.5) within group (
                                   order by extract(epoch from (ei.exited_at-ei.entered_at))/86400.0
                               ) as median_days,
                               percentile_cont(0.75) within group (
                                   order by extract(epoch from (ei.exited_at-ei.entered_at))/86400.0
                               ) as p75_days,
                               percentile_cont(0.90) within group (
                                   order by extract(epoch from (ei.exited_at-ei.entered_at))/86400.0
                               ) as p90_days
                        from event_intervals ei
                        join public.applications a on a.id=ei.application_id
                        join public.jobs j on j.id=a.job_id
                        where {' and '.join(duration_clauses)}
                        group by ei.new_stage
                        order by min(ei.entered_at), ei.new_stage""",
                    [organization_id, *duration_params],
                )
                waiting_time = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    f"""select a.status, count(distinct a.id)::int as distinct_applications
                        from public.application_stage_history h
                        join public.applications a on a.id=h.application_id
                        join public.jobs j on j.id=a.job_id
                        where {where}
                        group by a.status""",
                    params,
                )
                outcomes = {row["status"]: row["distinct_applications"] for row in cursor.fetchall()}
                cursor.execute(
                    f"""select count(distinct h.application_id)::int as cohort_size
                        from public.application_stage_history h
                        join public.applications a on a.id=h.application_id
                        join public.jobs j on j.id=a.job_id
                        where {where}""",
                    params,
                )
                cohort_size = cursor.fetchone()["cohort_size"] or 0
        total = cohort_size
        return {
            "filters": {
                "organization_id": str(organization_id),
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "job_id": str(job_id) if job_id else None,
                "recruiter_id": str(recruiter_id) if recruiter_id else None,
                "cohort": "stage_event_created_at",
            },
            "sample_size": cohort_size,
            "low_sample_size": total < 5,
            "stages": stages,
            "stage_waiting_time": waiting_time,
            "outcomes": outcomes,
            "limitations": [
                "Stage-entry events are counted from recorded history; applications with no history event are not represented in stage counts.",
                "Distinct application counts by stage are not mutually exclusive and must not be summed as a total funnel population.",
                "Waiting time uses the next recorded stage-history timestamp; open intervals with no later event are excluded.",
                "Timestamps tied to the same instant are ordered by event ID because the source schema has no explicit transition sequence.",
            ],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc


@router.get("/workload")
async def analytics_workload(
    organization_id: UUID,
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Show assigned work and unassigned demand without treating counts as productivity scores."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """with member_scope as (
                           select m.user_id, m.role, p.full_name
                           from public.organization_members m
                           left join public.profiles p on p.id=m.user_id
                           where m.organization_id=%s
                             and (%s::uuid is null or m.user_id=%s::uuid)
                       ),
                       job_counts as (
                           select j.recruiter_id as user_id,
                                  count(*) filter (where j.status='open')::int as open_vacancies,
                                  count(*) filter (where j.status='on_hold')::int as on_hold_vacancies
                           from public.jobs j
                           where j.organization_id=%s and j.recruiter_id is not null
                           group by j.recruiter_id
                       ),
                       application_counts as (
                           select j.recruiter_id as user_id,
                                  count(distinct a.id) filter (
                                      where a.status not in ('hired','rejected','withdrawn')
                                  )::int as active_applications
                           from public.applications a
                           join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                           where a.organization_id=%s and j.recruiter_id is not null
                           group by j.recruiter_id
                       ),
                       interview_counts as (
                           select j.recruiter_id as user_id,
                                  count(distinct i.id)::int as upcoming_interviews
                           from public.interviews i
                           join public.applications a on a.id=i.application_id and a.organization_id=i.organization_id
                           join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                           where i.organization_id=%s
                             and i.status in ('scheduled','rescheduled')
                             and i.scheduled_at >= now()
                             and j.recruiter_id is not null
                           group by j.recruiter_id
                       ),
                       task_counts as (
                           select t.assigned_to as user_id,
                                  count(*) filter (
                                      where t.completed_at is null and t.due_at < now()
                                  )::int as overdue_tasks,
                                  count(*) filter (
                                      where t.completed_at is null
                                  )::int as open_tasks
                           from public.recruiter_tasks t
                           where t.organization_id=%s and t.assigned_to is not null
                           group by t.assigned_to
                       )
                       select ms.user_id, ms.role, coalesce(ms.full_name, 'Unnamed user') as name,
                              coalesce(jc.open_vacancies,0)::int as open_vacancies,
                              coalesce(jc.on_hold_vacancies,0)::int as on_hold_vacancies,
                              coalesce(ac.active_applications,0)::int as active_applications,
                              coalesce(ic.upcoming_interviews,0)::int as upcoming_interviews,
                              coalesce(tc.open_tasks,0)::int as open_tasks,
                              coalesce(tc.overdue_tasks,0)::int as overdue_tasks
                       from member_scope ms
                       left join job_counts jc on jc.user_id=ms.user_id
                       left join application_counts ac on ac.user_id=ms.user_id
                       left join interview_counts ic on ic.user_id=ms.user_id
                       left join task_counts tc on tc.user_id=ms.user_id
                       order by ms.full_name nulls last, ms.user_id""",
                    [organization_id, recruiter_id, recruiter_id, organization_id,
                     organization_id, organization_id, organization_id],
                )
                recruiters = [
                    {**dict(row), "user_id": str(row["user_id"])}
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    """select
                           count(*) filter (where j.status='open' and j.recruiter_id is null)::int as unassigned_open_vacancies,
                           (select count(*)::int from public.recruiter_tasks t
                            where t.organization_id=%s and t.assigned_to is null and t.completed_at is null)
                             as unassigned_open_tasks
                       from public.jobs j
                       where j.organization_id=%s""",
                    [organization_id, organization_id],
                )
                unassigned = dict(cursor.fetchone())
        return {
            "organization_id": str(organization_id),
            "recruiters": recruiters,
            "unassigned": unassigned,
            "definitions": {
                "open_tasks": "Tasks with completed_at IS NULL",
                "overdue_tasks": "Open tasks with due_at earlier than the current database time",
                "upcoming_interviews": "Scheduled or rescheduled interviews at or after the current database time",
                "capacity_score": None,
                "note": "These counts describe workload, not recruiter productivity or performance.",
            },
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc


@router.get("/sources")
async def analytics_sources(
    organization_id: UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Compare application sources using raw attribution labels and distinct recruitment records."""
    assert_org_member(user_id, organization_id)
    _validate_dates(date_from, date_to)
    app_where, app_params = _application_scope(
        organization_id, date_from, date_to, job_id, recruiter_id
    )
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select coalesce(nullif(btrim(a.source), ''), 'Unknown') as source,
                               count(distinct a.id)::int as applications,
                               count(distinct a.id) filter (
                                   where a.status in ('submitted','interview','offer','hired')
                               )::int as qualified_applications,
                               count(distinct i.id) filter (
                                   where i.status='completed'
                               )::int as completed_interviews,
                               count(distinct o.id)::int as offers,
                               count(distinct o.id) filter (
                                   where o.status in ('accepted','rejected')
                               )::int as decided_offers,
                               count(distinct o.id) filter (
                                   where o.status='accepted'
                               )::int as accepted_offers,
                               count(distinct a.id) filter (
                                   where a.status='hired'
                               )::int as hires
                        from public.applications a
                        join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                        left join public.interviews i
                          on i.application_id=a.id and i.organization_id=a.organization_id
                        left join public.offers o
                          on o.application_id=a.id and o.organization_id=a.organization_id
                        where {app_where}
                        group by coalesce(nullif(btrim(a.source), ''), 'Unknown')
                        order by applications desc, source asc""",
                    app_params,
                )
                rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["offer_acceptance_rate"] = (
                row["accepted_offers"] / row["decided_offers"]
                if row["decided_offers"] else None
            )
            row["conversion_rate"] = (
                row["hires"] / row["applications"] if row["applications"] else None
            )
            row["sample_warning"] = row["applications"] < 5
        return {
            "definitions_version": "1.0",
            "filters": {
                "organization_id": str(organization_id),
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "job_id": str(job_id) if job_id else None,
                "recruiter_id": str(recruiter_id) if recruiter_id else None,
                "cohort": "application_created_at",
            },
            "sources": rows,
            "limitations": [
                "Source is the raw applications.source value; blank and missing values are grouped as Unknown.",
                "Qualified application means current status submitted, interview, offer or hired.",
                "Source association is descriptive and does not establish causation.",
                "Campaign spend and ROI are not included because campaign attribution and currency comparability need separate validation.",
            ],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc
