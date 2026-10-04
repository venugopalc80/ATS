from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.interviews import InterviewCreate, InterviewOut, InterviewUpdate
from app.services.interview_service import InterviewService

router=APIRouter(prefix="/api/interviews",tags=["interviews"])
service=InterviewService()

@router.get("",response_model=list[InterviewOut])
async def list_interviews(organization_id:UUID,status:str|None=Query(default=None),user_id:UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id)
    try:return [InterviewOut.model_validate(x) for x in await service.list_interviews(organization_id,status)]
    except (DatabaseConfigurationError,DatabaseConnectionError) as exc:raise HTTPException(503,"Database operation failed") from exc

@router.post("",response_model=InterviewOut,status_code=201)
async def create_interview(payload:InterviewCreate,user_id:UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,payload.organization_id)
    try:return InterviewOut.model_validate(await service.create_interview(payload,user_id))
    except (DatabaseConfigurationError,DatabaseConnectionError) as exc:raise HTTPException(503,"Database operation failed") from exc

@router.get("/{interview_id}",response_model=InterviewOut)
async def get_interview(interview_id:UUID,user_id:UUID=Depends(get_current_user_id)):
    row=await service.get_interview(interview_id)
    if row is None:raise HTTPException(404,"Interview not found")
    assert_org_member(user_id,row["organization_id"]); return InterviewOut.model_validate(row)

@router.patch("/{interview_id}",response_model=InterviewOut)
async def update_interview(interview_id:UUID,payload:InterviewUpdate,user_id:UUID=Depends(get_current_user_id)):
    row=await service.get_interview(interview_id)
    if row is None:raise HTTPException(404,"Interview not found")
    assert_org_member(user_id,row["organization_id"])
    return InterviewOut.model_validate(await service.update_interview(interview_id,payload))
