from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.application_sla import ApplicationSLADeadlineOut, ApplicationSLAPolicyOut, ApplicationSLAPolicyUpdate
from app.services.application_sla_service import ApplicationSLADueService

router = APIRouter(prefix="/api/applications", tags=["application SLA"])
COLUMNS = (
    "organization_id, initial_review_minutes, first_recruiter_action_minutes, "
    "candidate_follow_up_minutes, post_interview_update_minutes, timezone, "
    "business_days_only, business_hours_start, business_hours_end, working_days, "
    "enabled, updated_by, created_at, updated_at"
)


def _database_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("/sla-policy", response_model=ApplicationSLAPolicyOut)
async def get_sla_policy(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationSLAPolicyOut:
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select " + COLUMNS + " from public.application_sla_policies "
                    "where organization_id=%s",
                    [organization_id],
                )
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="SLA policy not configured")
        return ApplicationSLAPolicyOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.put("/sla-policy", response_model=ApplicationSLAPolicyOut)
async def update_sla_policy(
    payload: ApplicationSLAPolicyUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationSLAPolicyOut:
    assert_org_admin(user_id, payload.organization_id)
    try:
        data = payload.model_dump(mode="python", exclude={"organization_id"})
        columns = list(data)
        values = [data[column] for column in columns]
        assignments = ", ".join(f"{column}=excluded.{column}" for column in columns)
        query = (
            "insert into public.application_sla_policies "
            "(organization_id, " + ", ".join(columns) + ", updated_by) "
            "values (" + ", ".join(["%s"] * (len(columns) + 1)) + ", %s) "
            "on conflict (organization_id) do update set " + assignments
            + ", updated_by=excluded.updated_by, updated_at=now() "
            "returning " + COLUMNS
        )
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, [payload.organization_id, *values, user_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=503, detail="SLA policy could not be saved")
        return ApplicationSLAPolicyOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


deadline_service = ApplicationSLADueService()


@router.post("/{application_id}/sla-deadlines/recalculate", response_model=list[ApplicationSLADeadlineOut])
async def recalculate_application_sla_deadlines(
    application_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationSLADeadlineOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await deadline_service.recalculate_initial_deadlines(
            application_id, organization_id
        )
        if not rows:
            raise HTTPException(
                status_code=404,
                detail="Application or enabled SLA policy not found",
            )
        return [ApplicationSLADeadlineOut.model_validate(row) for row in rows]
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{application_id}/sla-deadlines", response_model=list[ApplicationSLADeadlineOut])
async def list_application_sla_deadlines(
    application_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationSLADeadlineOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await deadline_service.list_deadlines(application_id, organization_id)
        return [ApplicationSLADeadlineOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/sla-deadlines/refresh-overdue", response_model=list[dict])
async def refresh_overdue_application_sla_deadlines(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[dict]:
    assert_org_admin(user_id, organization_id)
    try:
        return await deadline_service.refresh_overdue(organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
