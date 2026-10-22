from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.requisitions import RequisitionCreate, RequisitionOut, RequisitionUpdate
from app.services.requisition_service import RequisitionService

router = APIRouter(prefix="/api/requisitions", tags=["requisitions"])
service = RequisitionService()
ADMINS = {"owner", "admin"}

def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")

async def authorised_row(requisition_id: UUID, user_id: UUID):
    try:
        row = await service.get_requisition(requisition_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Requisition not found")
    assert_org_member(user_id, row["organization_id"])
    return row

class DecisionBody(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)

class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)

@router.get("", response_model=list[RequisitionOut])
async def list_requisitions(organization_id: UUID, status: str | None = Query(default=None, pattern="^(draft|pending_approval|approved|rejected|converted|cancelled)$"), search: str | None = Query(default=None, max_length=120), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        return [RequisitionOut.model_validate(row) for row in await service.list_requisitions(organization_id, status, search, limit, offset)]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("", response_model=RequisitionOut, status_code=201)
async def create_requisition(payload: RequisitionCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    role = get_org_role(user_id, payload.organization_id)
    if role not in ADMINS | {"hiring_manager", "recruiter"}:
        raise HTTPException(status_code=403, detail="Your organisation role cannot request vacancies")
    try:
        return RequisitionOut.model_validate(await service.create_requisition(payload, user_id))
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.get("/{requisition_id}", response_model=RequisitionOut)
async def get_requisition(requisition_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    return RequisitionOut.model_validate(await authorised_row(requisition_id, user_id))

@router.patch("/{requisition_id}", response_model=RequisitionOut)
async def update_requisition(requisition_id: UUID, payload: RequisitionUpdate, user_id: UUID = Depends(get_current_user_id)):
    row = await authorised_row(requisition_id, user_id)
    role = get_org_role(user_id, row["organization_id"])
    if row["status"] not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Only draft or rejected requisitions can be edited")
    if role not in ADMINS and not (role in {"hiring_manager", "recruiter"} and row["requested_by"] == user_id):
        raise HTTPException(status_code=403, detail="You cannot edit this requisition")
    try:
        updated = await service.update_requisition(requisition_id, payload, user_id)
        return RequisitionOut.model_validate(updated)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("/{requisition_id}/submit", response_model=RequisitionOut)
async def submit_requisition(requisition_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    row = await authorised_row(requisition_id, user_id)
    role = get_org_role(user_id, row["organization_id"])
    if role not in ADMINS and not (role in {"hiring_manager", "recruiter"} and row["requested_by"] == user_id):
        raise HTTPException(status_code=403, detail="You cannot submit this requisition")
    try:
        updated = await service.submit(requisition_id, user_id)
        if updated is None:
            raise HTTPException(status_code=409, detail="Only draft or rejected requisitions can be submitted")
        return RequisitionOut.model_validate(updated)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("/{requisition_id}/approve", response_model=RequisitionOut)
async def approve_requisition(requisition_id: UUID, payload: DecisionBody, user_id: UUID = Depends(get_current_user_id)):
    row = await authorised_row(requisition_id, user_id)
    if get_org_role(user_id, row["organization_id"]) not in ADMINS:
        raise HTTPException(status_code=403, detail="Only organisation owners or admins can approve requisitions")
    try:
        updated = await service.decide(requisition_id, user_id, True, payload.comment or "")
        if updated is None:
            raise HTTPException(status_code=409, detail="Only pending requisitions can be approved")
        return RequisitionOut.model_validate(updated)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("/{requisition_id}/reject", response_model=RequisitionOut)
async def reject_requisition(requisition_id: UUID, payload: RejectBody, user_id: UUID = Depends(get_current_user_id)):
    row = await authorised_row(requisition_id, user_id)
    if get_org_role(user_id, row["organization_id"]) not in ADMINS:
        raise HTTPException(status_code=403, detail="Only organisation owners or admins can reject requisitions")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A rejection reason is required")
    try:
        updated = await service.decide(requisition_id, user_id, False, reason)
        if updated is None:
            raise HTTPException(status_code=409, detail="Only pending requisitions can be rejected")
        return RequisitionOut.model_validate(updated)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("/{requisition_id}/convert-to-job")
async def convert_to_job(requisition_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    row = await authorised_row(requisition_id, user_id)
    if get_org_role(user_id, row["organization_id"]) not in ADMINS | {"recruiter"}:
        raise HTTPException(status_code=403, detail="You cannot convert this requisition to a job")
    try:
        result = await service.convert_to_job(requisition_id, user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Requisition not found")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
