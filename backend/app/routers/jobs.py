from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.jobs import JobCreate, JobOut, JobUpdate
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
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_job(payload)
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
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_job(job_id, payload)
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        deleted = await service.delete_job(job_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
