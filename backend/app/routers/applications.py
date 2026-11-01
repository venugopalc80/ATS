from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.applications import ApplicationCreate, ApplicationOut, ApplicationUpdate
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/api/applications", tags=["applications"])
service = ApplicationService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    organization_id: UUID,
    status: str | None = Query(default=None),
    job_id: UUID | None = Query(default=None),
    candidate_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationOut]:
    require_permission(user_id, organization_id, "application.read")
    try:
        rows = await service.list_applications(organization_id, status, job_id, candidate_id)
        return [ApplicationOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    require_permission(user_id, payload.organization_id, "application.manage")
    try:
        row = await service.create_application(payload)
        return ApplicationOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        organization_id = await service.get_application_organization_id(application_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Application not found")
        require_permission(user_id, organization_id, "application.read")
        row = await service.get_application(application_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return ApplicationOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        organization_id = await service.get_application_organization_id(application_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Application not found")
        require_permission(user_id, organization_id, "application.manage")
        row = await service.update_application(application_id, payload, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return ApplicationOut.model_validate(row)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{application_id}", status_code=204)
async def delete_application(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        organization_id = await service.get_application_organization_id(application_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Application not found")
        require_permission(user_id, organization_id, "application.delete")
        deleted = await service.delete_application(application_id)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
