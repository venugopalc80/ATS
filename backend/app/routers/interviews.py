from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.interviews import InterviewCreate, InterviewOut, InterviewUpdate
from app.services.interview_service import InterviewService

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
service = InterviewService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[InterviewOut])
async def list_interviews(
    organization_id: UUID,
    status: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_interviews(organization_id, status)
        return [InterviewOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=InterviewOut, status_code=201)
async def create_interview(
    payload: InterviewCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_interview(payload, user_id)
        return InterviewOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(
    interview_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        row = await service.get_interview(interview_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    assert_org_member(user_id, row["organization_id"])
    return InterviewOut.model_validate(row)


@router.patch("/{interview_id}", response_model=InterviewOut)
async def update_interview(
    interview_id: UUID,
    payload: InterviewUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        existing = await service.get_interview(interview_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_interview(interview_id, payload, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return InterviewOut.model_validate(row)
