from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.application_assignments import (
    ApplicationAssignmentHistoryOut,
    ApplicationAssignmentOut,
    ApplicationAssignmentUpdate,
)
from app.services.application_assignment_service import ApplicationAssignmentService

router = APIRouter(prefix="/api/applications", tags=["application assignments"])
service = ApplicationAssignmentService()


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")

def _get_application_for_member(application_id: UUID, user_id: UUID):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select a.organization_id from public.applications a "
                "where a.id=%s and exists (select 1 from public.organization_members om "
                "where om.organization_id=a.organization_id and om.user_id=%s)",
                [application_id, user_id],
            )
            return cursor.fetchone()


@router.put("/{application_id}/assignment", response_model=ApplicationAssignmentOut)
async def set_application_assignment(
    application_id: UUID,
    payload: ApplicationAssignmentUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationAssignmentOut:
    try:
        # Only organisation owners/admins can allocate work to another recruiter.
        application = _get_application_for_member(application_id, user_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        assert_org_admin(user_id, application["organization_id"])
        row = await service.assign(
            application_id, payload.recruiter_id, user_id, payload.reason
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return ApplicationAssignmentOut.model_validate(row)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/{application_id}/assignment", response_model=ApplicationAssignmentOut)
async def get_application_assignment(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationAssignmentOut:
    try:
        application = _get_application_for_member(application_id, user_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        assert_org_member(user_id, application["organization_id"])
        row = await service.get(application_id, application["organization_id"])
        if row is None:
            raise HTTPException(status_code=404, detail="Assignment not found")
        return ApplicationAssignmentOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/{application_id}/assignment/history", response_model=list[ApplicationAssignmentHistoryOut])
async def get_application_assignment_history(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationAssignmentHistoryOut]:
    try:
        application = _get_application_for_member(application_id, user_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        assert_org_member(user_id, application["organization_id"])
        rows = await service.history(application_id, application["organization_id"])
        return [ApplicationAssignmentHistoryOut.model_validate(row) for row in rows]
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/recruiters", response_model=list[dict])
async def list_organisation_recruiters(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[dict]:
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select m.user_id as id, p.full_name, p.email "
                    "from public.organization_members m "
                    "left join public.profiles p on p.id=m.user_id "
                    "where m.organization_id=%s and m.role='recruiter' "
                    "order by coalesce(p.full_name, p.email, m.user_id::text)",
                    [organization_id],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/assignments", response_model=list[ApplicationAssignmentOut])
async def list_organisation_assignments(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationAssignmentOut]:
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select " + "application_id, organization_id, recruiter_id, assigned_by, assigned_at, updated_at "
                    "from public.application_assignments where organization_id=%s",
                    [organization_id],
                )
                return [ApplicationAssignmentOut.model_validate(row) for row in cursor.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
