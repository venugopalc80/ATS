from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
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

@router.get("/latest", response_model=list[dict])
async def latest_notes(
    organization_id: UUID,
    candidate_ids: list[UUID] = Query(..., min_length=1, max_length=50),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select distinct on (rn.candidate_id)
                        rn.candidate_id, rn.note, rn.created_at, rn.author_user_id
                    from public.recruiter_notes rn
                    join public.candidates c on c.id = rn.candidate_id
                    where rn.organization_id = %s
                      and c.organization_id = %s
                      and rn.candidate_id = any(%s)
                    order by rn.candidate_id, rn.created_at desc
                    """,
                    [organization_id, organization_id, candidate_ids],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc
