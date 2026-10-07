from typing import Any
from uuid import UUID
from app.db import get_connection
from app.schemas.notes import NoteCreate
class NoteService:
    async def list_candidate_notes(self,organization_id:UUID,candidate_id:UUID)->list[dict[str,Any]]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select id,organization_id,candidate_id,author_user_id,note,created_at,updated_at from public.recruiter_notes where organization_id=%s and candidate_id=%s order by created_at desc",[organization_id,candidate_id]);return list(cursor.fetchall())
    async def create_note(self,payload:NoteCreate,author_user_id:UUID)->dict[str,Any]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.recruiter_notes (organization_id,candidate_id,author_user_id,note) values (%s,%s,%s,%s) returning id,organization_id,candidate_id,author_user_id,note,created_at,updated_at",[payload.organization_id,payload.candidate_id,author_user_id,payload.note.strip()]);row=cursor.fetchone()
                if row is None: raise RuntimeError("Note was not created")
                return row
