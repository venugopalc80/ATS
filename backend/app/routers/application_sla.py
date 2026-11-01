from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.application_sla import ApplicationSLAPolicyOut, ApplicationSLAPolicyUpdate

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
