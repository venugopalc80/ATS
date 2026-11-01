from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.applications import (
    ApplicationBulkTransition,
    ApplicationBulkTransitionOut,
    ApplicationCreate,
    ApplicationOut,
    ApplicationStageConfigOut,
    ApplicationStageConfigUpdate,
    ApplicationStageHistoryOut,
    ApplicationTransition,
    ApplicationUpdate,
)
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
        row = await service.create_application(payload, user_id)
        return ApplicationOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("/{application_id}/transition", response_model=ApplicationOut)
async def transition_application(
    application_id: UUID,
    payload: ApplicationTransition,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        existing = await service.get_application_for_member(application_id, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        row = await service.transition_application(
            application_id,
            payload.status,
            user_id,
            payload.reason,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return ApplicationOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{application_id}/history", response_model=list[ApplicationStageHistoryOut])
async def get_application_history(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationStageHistoryOut]:
    try:
        existing = await service.get_application_for_member(application_id, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        rows = await service.list_stage_history(existing["organization_id"], application_id)
        return [ApplicationStageHistoryOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/stages", response_model=list[ApplicationStageConfigOut])
async def list_application_stages(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> list[ApplicationStageConfigOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_stage_config(organization_id)
        return [ApplicationStageConfigOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.patch("/stages/{stage_key}", response_model=ApplicationStageConfigOut)
async def update_application_stage(
    stage_key: str,
    organization_id: UUID,
    payload: ApplicationStageConfigUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationStageConfigOut:
    assert_org_admin(user_id, organization_id)
    try:
        row = await service.update_stage_config(organization_id, stage_key, payload)
        if row is None:
            raise HTTPException(status_code=404, detail="Application stage not found")
        return ApplicationStageConfigOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("/bulk-transition", response_model=ApplicationBulkTransitionOut)
async def bulk_transition_applications(
    payload: ApplicationBulkTransition,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationBulkTransitionOut:
    """Transition up to 100 applications independently and report partial failures."""
    results = []
    for index, application_id in enumerate(payload.application_ids):
        try:
            existing = await service.get_application_for_member(application_id, user_id)
            # Use the same not-found response for absent and cross-tenant records.
            if existing is None:
                raise HTTPException(status_code=404, detail="Application not found")
            try:
                    except HTTPException as exc:
                if exc.status_code in (401, 403, 404):
                    raise HTTPException(status_code=404, detail="Application not found") from exc
                raise

            row = await service.transition_application(
                application_id,
                payload.status,
                user_id,
                payload.reason,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="Application not found")
            results.append({
                "application_id": application_id,
                "success": True,
                "status": row["status"],
                "error": None,
            })
        except HTTPException as exc:
            results.append({
                "application_id": application_id,
                "success": False,
                "status": None,
                "error": "Application not found" if exc.status_code == 404 else str(exc.detail),
            })
        except ValueError as exc:
            results.append({
                "application_id": application_id,
                "success": False,
                "status": None,
                "error": str(exc),
            })
        except (DatabaseConfigurationError, DatabaseConnectionError):
            # Earlier items may already have committed. Preserve those outcomes and
            # explicitly mark the current and remaining items as not processed
            # instead of returning a 503 that hides partial completion.
            results.append({
                "application_id": application_id,
                "success": False,
                "status": None,
                "error": "Database unavailable; this application was not processed.",
            })
            for pending_id in payload.application_ids[index + 1:]:
                results.append({
                    "application_id": pending_id,
                    "success": False,
                    "status": None,
                    "error": "Not processed because the database became unavailable.",
                })
            break

    succeeded = sum(1 for item in results if item["success"])
    return ApplicationBulkTransitionOut(
        requested=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        row = await service.get_application_for_member(application_id, user_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationOut.model_validate(row)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> ApplicationOut:
    try:
        existing = await service.get_application_for_member(application_id, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        if "status" in payload.model_fields_set:
            raise HTTPException(
                status_code=409,
                detail="Application stage changes must use the transition endpoint with a reason",
            )
        row = await service.update_application(application_id, payload, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
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
        existing = await service.get_application_for_member(application_id, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Application not found")
        deleted = await service.delete_application(application_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
