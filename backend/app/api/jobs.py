from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.schemas.jobs import JobCreate, JobOut

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(organization_id: UUID) -> list[JobOut]:
    # Supabase persistence will be wired here after environment configuration.
    return []


@router.post("", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate) -> JobOut:
    raise HTTPException(status_code=501, detail="Database persistence is not configured yet")
