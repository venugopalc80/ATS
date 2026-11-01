from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.jobs import JobCreate, JobOut, JobUpdate
from app.services.google_indexing import notify_google_indexing
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
service = JobService()

def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")

@router.get("", response_model=list[JobOut])
async def list_jobs(organization_id: UUID, status: str | None = Query(default=None), job_ids: list[UUID] | None = Query(default=None, max_length=100), user_id: UUID = Depends(get_current_user_id)) -> list[JobOut]:
    require_permission(user_id, organization_id, "job.read")
    try:
        rows = await service.list_jobs(organization_id, status, job_ids)
        return [JobOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate, background_tasks: BackgroundTasks, user_id: UUID = Depends(get_current_user_id)) -> JobOut:
    require_permission(user_id, payload.organization_id, "job.manage")
    try:
        row = await service.create_job(payload)
        if row.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: UUID, user_id: UUID = Depends(get_current_user_id)) -> JobOut:
    try:
        organization_id = await service.get_job_organization_id(job_id)
        if organization_id is None:
            raise HTTPException(404, "Job not found")
        require_permission(user_id, organization_id, "job.read")
        row = await service.get_job(job_id)
        if row is None:
            raise HTTPException(404, "Job not found")
        return JobOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.patch("/{job_id}", response_model=JobOut)
async def update_job(job_id: UUID, payload: JobUpdate, background_tasks: BackgroundTasks, user_id: UUID = Depends(get_current_user_id)) -> JobOut:
    try:
        organization_id = await service.get_job_organization_id(job_id)
        if organization_id is None:
            raise HTTPException(404, "Job not found")
        require_permission(user_id, organization_id, "job.manage")
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(404, "Job not found")
        row = await service.update_job(job_id, payload)
        if row is None:
            raise HTTPException(404, "Job not found")
        if row.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
        elif existing.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_DELETED")
        return JobOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: UUID, background_tasks: BackgroundTasks, user_id: UUID = Depends(get_current_user_id)) -> None:
    try:
        organization_id = await service.get_job_organization_id(job_id)
        if organization_id is None:
            raise HTTPException(404, "Job not found")
        require_permission(user_id, organization_id, "job.delete")
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(404, "Job not found")
        deleted = await service.delete_job(job_id)
        if deleted and existing.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(job_id), "URL_DELETED")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(404, "Job not found")
