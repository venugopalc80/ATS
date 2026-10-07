from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from app.auth import assert_org_member,get_current_user_id
from app.db import DatabaseConfigurationError,DatabaseConnectionError,get_connection
from app.schemas.notes import NoteCreate,NoteOut
from app.services.note_service import NoteService
router=APIRouter(prefix="/api/notes",tags=["notes"]);service=NoteService()
@router.get("/candidate/{candidate_id}",response_model=list[NoteOut])
async def list_notes(candidate_id:UUID,organization_id:UUID,user_id:UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.candidates where id=%s",[candidate_id]);row=cursor.fetchone()
        if row is None or row["organization_id"]!=organization_id: raise HTTPException(status_code=404,detail="Candidate not found")
        return [NoteOut.model_validate(x) for x in await service.list_candidate_notes(organization_id,candidate_id)]
    except HTTPException: raise
    except (DatabaseConfigurationError,DatabaseConnectionError) as exc: raise HTTPException(status_code=503,detail="Database operation failed") from exc
@router.post("",response_model=NoteOut,status_code=201)
async def create_note(payload:NoteCreate,user_id:UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.candidates where id=%s",[payload.candidate_id]);row=cursor.fetchone()
        if row is None or row["organization_id"]!=payload.organization_id: raise HTTPException(status_code=404,detail="Candidate not found")
        return NoteOut.model_validate(await service.create_note(payload,user_id))
    except HTTPException: raise
    except (DatabaseConfigurationError,DatabaseConnectionError) as exc: raise HTTPException(status_code=503,detail="Database operation failed") from exc
