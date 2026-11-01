from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.requisitions import RequisitionCreate, RequisitionOut, RequisitionUpdate
from app.services.requisition_service import RequisitionService

router = APIRouter(prefix="/api/requisitions", tags=["requisitions"])
service = RequisitionService()
ADMINS = {"owner", "admin"}

def validate_org_links(organization_id: UUID, client_id, hiring_manager_id, recruiter_id):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if client_id is not None:
                cursor.execute("select 1 from public.clients where id=%s and organization_id=%s", [client_id, organization_id])
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=422, detail="Client must belong to the same organisation")
            for label, assigned_user, allowed_roles in (
                ("Hiring manager", hiring_manager_id, {"owner", "admin", "hiring_manager"}),
                ("Recruiter", recruiter_id, {"owner", "admin", "recruiter"}),
            ):
                if assigned_user is not None:
                    cursor.execute("select role from public.organization_members where organization_id=%s and user_id=%s", [organization_id, assigned_user])
                    member = cursor.fetchone()
                    if member is None:
                        raise HTTPException(status_code=422, detail=label + " must belong to the same organisation")
                    if member["role"] not in allowed_roles:
                        raise HTTPException(status_code=422, detail=label + " must have an eligible organisation role")

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
        validate_org_links(payload.organization_id, payload.client_id, payload.hiring_manager_id, payload.recruiter_id)
        return RequisitionOut.model_validate(await service.create_requisition(payload, user_id))
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc



@router.get("/assignees")
async def list_requisition_assignees(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    """Return assignable team members for the caller's organisation only."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select m.user_id, p.full_name, p.email, m.role
                       from public.organization_members m
                       join public.profiles p on p.id = m.user_id
                       where m.organization_id = %s
                         and m.role in ('owner','admin','recruiter','hiring_manager')
                       order by coalesce(nullif(p.full_name, ''), p.email, m.user_id::text)""",
                    [organization_id],
                )
                rows = list(cursor.fetchall())
        return [{"user_id": str(row["user_id"]), "full_name": row["full_name"], "email": row["email"], "role": row["role"]} for row in rows]
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
    changes = payload.model_dump(exclude_unset=True)
    try:
        validate_org_links(row["organization_id"], changes.get("client_id", row["client_id"]), changes.get("hiring_manager_id", row["hiring_manager_id"]), changes.get("recruiter_id", row["recruiter_id"]))
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
