import csv
import io
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

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
                               "o.responded_at is not null",
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
                    """select count(*) filter (where j.status='open')::int as open_vacancies,
                              count(*) filter (where j.status='open'
                                  and coalesce(j.opened_at,j.created_at)::date < current_date - 30)::int
                                  as open_more_than_30_days,
                              count(*) filter (where j.status='open' and j.opened_at is null)::int
                                  as missing_opened_at,
                              percentile_cont(0.5) within group (
                                  order by current_date - coalesce(j.opened_at,j.created_at)::date
                              ) filter (where j.status='open') as median_days_open
                       from public.jobs j
                       where j.organization_id=%s
                         and j.status in ('open','on_hold')
                         and (%s::uuid is null or j.id=%s::uuid)
                         and (%s::uuid is null or j.recruiter_id=%s::uuid)""",
                    [organization_id, job_id, job_id, recruiter_id, recruiter_id],
                )
                vacancy_row = cursor.fetchone()

                fill_clauses = [
                    "jr.organization_id=%s",
                    "jr.status in ('approved','converted')",
                    "jr.approved_at is not null",
                    "j.organization_id=jr.organization_id",
                    "j.id=jr.job_id",
                ]
                fill_params = [organization_id]
                if date_from:
                    fill_clauses.append("jr.approved_at >= %s::date")
                    fill_params.append(date_from)
                if date_to:
                    fill_clauses.append("jr.approved_at < (%s::date + interval '1 day')")
                    fill_params.append(date_to)
                if job_id:
                    fill_clauses.append("jr.job_id=%s")
                    fill_params.append(job_id)
                if recruiter_id:
                    fill_clauses.append("coalesce(jr.recruiter_id,j.recruiter_id)=%s")
                    fill_params.append(recruiter_id)
                cursor.execute(
                    f"""select percentile_cont(0.5) within group (
                                  order by extract(epoch from (filled.accepted_at-jr.approved_at))/86400.0
                               ) as median_days,
                               count(*)::int as complete_requisitions
                        from public.job_requisitions jr
                        join public.jobs j on j.id=jr.job_id and j.organization_id=jr.organization_id
                        join lateral (
                            select min(o.responded_at) as accepted_at
                            from public.applications a
                            join public.offers o on o.application_id=a.id
                               and o.organization_id=a.organization_id
                            where a.organization_id=jr.organization_id
                              and a.job_id=jr.job_id
                              and o.status='accepted'
                              and o.responded_at is not null
                              and o.responded_at >= jr.approved_at
                        ) filled on filled.accepted_at is not null
                        where {' and '.join(fill_clauses)}""",
                    fill_params,
                )
                fill_row = cursor.fetchone()

        applications = application_row["applications"]
        decided_offers = offer_row["decided_offers"]
        accepted_offers = offer_row["accepted_offers"]
        complete_records = hire_row["complete_records"]
        fill_records = fill_row["complete_requisitions"]
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
                "median_time_to_fill_days": {
                    "value": float(fill_row["median_days"]) if fill_row["median_days"] is not None else None,
                    "complete_requisitions": fill_records,
                    "status": "available" if fill_records else "insufficient_complete_requisitions",
                    "definition": "Median calendar days from requisition approval to first accepted offer response for linked approved requisitions",
                },
                "vacancy_ageing": {
                    "median_days_open": float(vacancy_row["median_days_open"]) if vacancy_row["median_days_open"] is not None else None,
                    "open_more_than_30_days": vacancy_row["open_more_than_30_days"],
                    "missing_opened_at": vacancy_row["missing_opened_at"],
                    "age_anchor": "opened_at, falling back to job created_at",
                    "status": "available" if vacancy_row["open_vacancies"] else "empty_open_vacancy_cohort",
                },
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
                cursor.execute(
                    f"""with stage_map(stage, next_stage) as (
                            values ('new','screening'),
                                   ('screening','submitted'),
                                   ('submitted','interview'),
                                   ('interview','offer'),
                                   ('offer','hired')
                        ),
                        entries as (
                            select h.application_id, h.new_stage as stage,
                                   min(h.created_at) as entered_at
                            from public.application_stage_history h
                            join public.applications a on a.id=h.application_id
                            join public.jobs j on j.id=a.job_id
                            where {where}
                            group by h.application_id, h.new_stage
                        ),
                        conversion_flags as (
                            select e.application_id, e.stage, m.next_stage,
                                   exists (
                                       select 1
                                       from public.application_stage_history h2
                                       where h2.organization_id=%s
                                         and h2.application_id=e.application_id
                                         and h2.new_stage=m.next_stage
                                         and h2.created_at >= e.entered_at
                                   ) as reached_next
                            from entries e
                            join stage_map m on m.stage=e.stage
                        )
                        select stage, next_stage,
                               count(distinct application_id)::int as entered_applications,
                               count(distinct application_id) filter (
                                   where reached_next
                               )::int as reached_next_applications,
                               count(distinct application_id) filter (
                                   where reached_next
                               )::float / nullif(count(distinct application_id),0) as conversion_rate
                        from conversion_flags
                        group by stage, next_stage
                        order by case stage
                            when 'new' then 1 when 'screening' then 2
                            when 'submitted' then 3 when 'interview' then 4
                            when 'offer' then 5 else 99 end""",
                    [*params, organization_id],
                )
                stage_conversions = [dict(row) for row in cursor.fetchall()]
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
            "stage_conversions": stage_conversions,
            "outcomes": outcomes,
            "limitations": [
                "Stage-entry events are counted from recorded history; applications with no history event are not represented in stage counts.",
                "Distinct application counts by stage are not mutually exclusive and must not be summed as a total funnel population.",
                "Stage conversion uses the documented sequence new → screening → submitted → interview → offer → hired; it measures whether an application later reached the next named stage.",
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
                                      where t.status='open' and t.due_at < now()
                                  )::int as overdue_tasks,
                                  count(*) filter (
                                      where t.status='open'
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
                            where t.organization_id=%s and t.assigned_to is null and t.status='open')
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
                "open_tasks": "Tasks with status open; cancelled and completed tasks are excluded",
                "overdue_tasks": "Tasks with status open and due_at earlier than the current database time",
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


@router.get("/forecast")
async def analytics_forecast(
    organization_id: UUID,
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Provide an explainable baseline forecast from the last six complete months of approved headcount."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """with months as (
                           select generate_series(
                               date_trunc('month', current_date) - interval '6 months',
                               date_trunc('month', current_date) - interval '1 month',
                               interval '1 month'
                           )::date as month_start
                       ),
                       approved_demand as (
                           select date_trunc('month', jr.approved_at)::date as month_start,
                                  sum(jr.headcount)::int as approved_headcount,
                                  count(*)::int as approved_requisitions
                           from public.job_requisitions jr
                           left join public.jobs j
                             on j.id=jr.job_id and j.organization_id=jr.organization_id
                           where jr.organization_id=%s
                             and jr.status in ('approved','converted')
                             and jr.approved_at >= date_trunc('month', current_date) - interval '6 months'
                             and jr.approved_at < date_trunc('month', current_date)
                             and (%s::uuid is null or coalesce(jr.recruiter_id,j.recruiter_id)=%s::uuid)
                           group by date_trunc('month', jr.approved_at)::date
                       )
                       select m.month_start,
                              coalesce(d.approved_headcount,0)::int as approved_headcount,
                              coalesce(d.approved_requisitions,0)::int as approved_requisitions
                       from months m
                       left join approved_demand d using (month_start)
                       order by m.month_start""",
                    [organization_id, recruiter_id, recruiter_id],
                )
                history = [
                    {
                        "month": row["month_start"].isoformat(),
                        "approved_headcount": int(row["approved_headcount"] or 0),
                        "approved_requisitions": int(row["approved_requisitions"] or 0),
                    }
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    """select
                           coalesce(sum(jr.headcount),0)::int as pending_headcount,
                           count(*)::int as pending_requisitions
                       from public.job_requisitions jr
                       left join public.jobs j
                         on j.id=jr.job_id and j.organization_id=jr.organization_id
                       where jr.organization_id=%s
                         and jr.status='pending_approval'
                         and (%s::uuid is null or coalesce(jr.recruiter_id,j.recruiter_id)=%s::uuid)""",
                    [organization_id, recruiter_id, recruiter_id],
                )
                pending = dict(cursor.fetchone())
        nonzero_months = sum(1 for row in history if row["approved_requisitions"] > 0)
        average = (
            sum(row["approved_headcount"] for row in history) / len(history)
            if history else None
        )
        first_half = history[:3]
        second_half = history[3:]
        first_average = sum(row["approved_headcount"] for row in first_half) / len(first_half) if first_half else None
        second_average = sum(row["approved_headcount"] for row in second_half) / len(second_half) if second_half else None
        if first_average is None or second_average is None:
            trend = "insufficient_history"
        elif second_average > first_average:
            trend = "increasing"
        elif second_average < first_average:
            trend = "decreasing"
        else:
            trend = "stable"
        if nonzero_months == 0:
            confidence = "unavailable"
            status = "no_historical_approved_requisitions"
            forecast_value = None
        else:
            confidence = "low" if nonzero_months < 3 else "medium"
            status = "baseline_only"
            forecast_value = round(average, 1) if average is not None else None
        next_month = (date.today().replace(day=28) + timedelta(days=4)).replace(day=1)
        return {
            "organization_id": str(organization_id),
            "history_months": 6,
            "history": history,
            "forecast": {
                "month": next_month.isoformat(),
                "expected_approved_headcount": forecast_value,
                "pending_approval_headcount": pending["pending_headcount"],
                "pending_approval_requisitions": pending["pending_requisitions"],
                "trend": trend,
                "confidence": confidence,
                "status": status,
            },
            "methodology": {
                "baseline": "Arithmetic mean of approved requisition headcount across the last six complete calendar months, including zero-activity months.",
                "trend": "Compare average approved headcount in the first three history months with the most recent three history months.",
                "confidence": "Low when fewer than three of the six months contain approved requisitions; medium otherwise. This is an explainable baseline, not a statistical or machine-learning forecast.",
                "exclusions": ["Current partial month", "Rejected, cancelled and draft requisitions"],
            },
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc


@router.get("/export")
async def analytics_export(
    organization_id: UUID,
    report_type: Literal["kpis", "funnel", "workload", "sources", "forecast"] = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    recruiter_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    """Export an allowlisted analytics report as CSV; never accepts user-defined SQL or column expressions."""
    assert_org_member(user_id, organization_id)
    _validate_dates(date_from, date_to)
    if report_type == "kpis":
        payload = await analytics_kpis(
            organization_id=organization_id, date_from=date_from, date_to=date_to,
            job_id=job_id, recruiter_id=recruiter_id, user_id=user_id,
        )
        rows = [
            {"metric": name, **value}
            for name, value in payload["metrics"].items()
        ]
    elif report_type == "funnel":
        payload = await analytics_funnel(
            organization_id=organization_id, date_from=date_from, date_to=date_to,
            job_id=job_id, recruiter_id=recruiter_id, user_id=user_id,
        )
        waiting = {row["stage"]: row for row in payload["stage_waiting_time"]}
        conversion = {row["stage"]: row for row in payload["stage_conversions"]}
        stages = {row["stage"]: row for row in payload["stages"]}
        rows = []
        for stage in sorted(set(stages) | set(waiting) | set(conversion)):
            rows.append({
                "stage": stage,
                **stages.get(stage, {}),
                **waiting.get(stage, {}),
                **conversion.get(stage, {}),
            })
    elif report_type == "workload":
        payload = await analytics_workload(
            organization_id=organization_id, recruiter_id=recruiter_id, user_id=user_id,
        )
        rows = [{"record_type": "recruiter", **row} for row in payload["recruiters"]]
        rows.append({"record_type": "unassigned", **payload["unassigned"]})
    elif report_type == "sources":
        payload = await analytics_sources(
            organization_id=organization_id, date_from=date_from, date_to=date_to,
            job_id=job_id, recruiter_id=recruiter_id, user_id=user_id,
        )
        rows = payload["sources"]
    else:
        payload = await analytics_forecast(
            organization_id=organization_id, recruiter_id=recruiter_id, user_id=user_id,
        )
        rows = [{"record_type": "history", **row} for row in payload["history"]]
        rows.append({"record_type": "forecast", **payload["forecast"]})

    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    if not fieldnames:
        fieldnames = ["message"]
        rows = [{"message": "No rows available for this report and filter combination."}]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    filename = f"aqerith-{report_type}-report.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
