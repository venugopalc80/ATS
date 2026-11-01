from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.interviews import InterviewCreate, InterviewOut, InterviewUpdate
from app.services.interview_service import InterviewService

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
service = InterviewService()

@router.get("", response_model=list[InterviewOut])
async def list_interviews(organization_id: UUID, status: str | None = Query(default=None), candidate_id: UUID | None = Query(default=None), user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, organization_id, "interview.read")
    try:
        return [InterviewOut.model_validate(x) for x in await service.list_interviews(organization_id, status, candidate_id)]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

@router.post("", response_model=InterviewOut, status_code=201)
async def create_interview(payload: InterviewCreate, user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, payload.organization_id, "interview.manage")
    try:
        return InterviewOut.model_validate(await service.create_interview(payload, user_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

async def _interview_organization_id(interview_id: UUID) -> UUID | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select organization_id from public.interviews where id = %s", [interview_id])
            row = cursor.fetchone()
            return UUID(str(row["organization_id"])) if row else None

@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(interview_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        organization_id = await _interview_organization_id(interview_id)
        if organization_id is None:
            raise HTTPException(404, "Interview not found")
        require_permission(user_id, organization_id, "interview.read")
        row = await service.get_interview(interview_id)
        if row is None:
            raise HTTPException(404, "Interview not found")
        return InterviewOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

@router.patch("/{interview_id}", response_model=InterviewOut)
async def update_interview(interview_id: UUID, payload: InterviewUpdate, user_id: UUID = Depends(get_current_user_id)):
    try:
        organization_id = await _interview_organization_id(interview_id)
        if organization_id is None:
            raise HTTPException(404, "Interview not found")
        require_permission(user_id, organization_id, "interview.manage")
        row = await service.update_interview(interview_id, payload, user_id)
        if row is None:
            raise HTTPException(404, "Interview not found")
        return InterviewOut.model_validate(row)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc
