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
                                  order by extract(epoch from (o.responded_at - a.created_at)) / 86400.0
                               ) as median_days,
                               count(*)::int as complete_records
                        from public.applications a
                        join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                        join public.offers o on o.application_id=a.id and o.organization_id=a.organization_id
                        where {app_where}
                          and o.status='accepted'
                          and o.responded_at is not null
                          and o.responded_at >= a.created_at""",
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
            "sample_size": len({stage["stage"] for stage in stages}),
            "low_sample_size": total < 5,
            "stages": stages,
            "outcomes": outcomes,
            "limitations": [
                "Stage-entry events are counted from recorded history; applications with no history event are not represented in stage counts.",
                "Distinct application counts by stage are not mutually exclusive and must not be summed as a total funnel population.",
                "Waiting-time percentiles require validated stage-entry/exit semantics and are not included in this initial endpoint.",
            ],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Analytics data is temporarily unavailable") from exc
