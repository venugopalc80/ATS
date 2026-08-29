from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.db import DatabaseConfigurationError
from app.schemas.jobs import JobCreate, JobOut
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
service = JobService()


@router.get("", response_model=list[JobOut])
async def list_jobs(
    organization_id: UUID,
    status: str | None = Query(default=None),
) -> list[JobOut]:
    try:
        rows = await service.list_jobs(organization_id, status)
        return [JobOut.model_validate(row) for row in rows]
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate) -> JobOut:
    try:
        row = await service.create_job(payload)
        return JobOut.model_validate(row)
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: UUID) -> JobOut:
    try:
        row = await service.get_job(job_id)
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobOut.model_validate(row)
