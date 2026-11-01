from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_org_admin, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
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


@router.put("/{application_id}/assignment", response_model=ApplicationAssignmentOut)
async def set_application_assignment(
    application_id: UUID,
    payload: ApplicationAssignmentUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationAssignmentOut:
    try:
        # Only organisation owners/admins can allocate work to another recruiter.
        with __import__("app.db", fromlist=["get_connection"]).get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id from public.applications where id=%s",
                    [application_id],
                )
                application = cursor.fetchone()
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
        with __import__("app.db", fromlist=["get_connection"]).get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id from public.applications where id=%s",
                    [application_id],
                )
                application = cursor.fetchone()
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        from app.auth import assert_org_member
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
        with __import__("app.db", fromlist=["get_connection"]).get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id from public.applications where id=%s",
                    [application_id],
                )
                application = cursor.fetchone()
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        from app.auth import assert_org_member
        assert_org_member(user_id, application["organization_id"])
        rows = await service.history(application_id, application["organization_id"])
        return [ApplicationAssignmentHistoryOut.model_validate(row) for row in rows]
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
