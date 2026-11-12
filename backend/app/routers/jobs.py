from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.jobs import JobCreate, JobOut, JobUpdate
from app.services.google_indexing import notify_google_indexing
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
service = JobService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[JobOut])
async def list_jobs(
    organization_id: UUID,
    status: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
) -> list[JobOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_jobs(organization_id, status)
        return [JobOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_job(payload)
        if row.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    try:
        row = await service.get_job(job_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    assert_org_member(user_id, row["organization_id"])
    return JobOut.model_validate(row)


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_job(job_id, payload)
        if row is not None:
            if row.get("status") == "open":
                background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
            elif existing.get("status") == "open":
                background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_DELETED")
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        google_selected = False
        if existing.get("status") == "open":
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select selected from public.job_distribution_channels
                           where organization_id = %s and job_id = %s and channel_id = 'google'""",
                        [existing["organization_id"], job_id],
                    )
                    distribution = cursor.fetchone()
                    google_selected = bool(distribution and distribution["selected"])
        deleted = await service.delete_job(job_id)
        if deleted and google_selected:
            background_tasks.add_task(
                notify_google_indexing, str(job_id), "URL_DELETED", True
            )
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
