from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
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
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_applications(organization_id, status, job_id, candidate_id)
        return [ApplicationOut.model_validate(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_application(payload)
        return ApplicationOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        row = await service.get_application(application_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    assert_org_member(user_id, row["organization_id"])
    return ApplicationOut.model_validate(row)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        existing = await service.get_application(application_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_application(application_id, payload, user_id)
        return ApplicationOut.model_validate(row)
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
        existing = await service.get_application(application_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        assert_org_member(user_id, existing["organization_id"])
        deleted = await service.delete_application(application_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
