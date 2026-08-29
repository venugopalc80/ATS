from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.schemas.jobs import JobCreate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(organization_id: UUID, status: str | None = None):
    """Placeholder until the Supabase repository is wired into the API."""
    return {"items": [], "organization_id": str(organization_id), "status": status}


@router.post("", status_code=201)
async def create_job(payload: JobCreate):
    """Validate a requisition payload; persistence is enabled after Supabase configuration."""
    return {"message": "Job payload validated", "job": payload.model_dump(mode="json")}


@router.get("/{job_id}")
async def get_job(job_id: UUID):
    raise HTTPException(status_code=404, detail="Job not found")
