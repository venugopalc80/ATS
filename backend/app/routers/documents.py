import hashlib
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from supabase import create_client

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/documents", tags=["candidate documents"])
BUCKET = "candidate-documents"
MAX_BYTES = 5 * 1024 * 1024
ALLOWED = {
    "application/pdf": (".pdf", b"%PDF-"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx", b"PK\x03\x04"),
}


class DocumentOut(BaseModel):
    id: UUID
    organization_id: UUID
    candidate_id: UUID
    application_id: UUID | None = None
    document_type: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    sha256: str
    created_at: str | None = None


def storage_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Private document storage is not configured")
    return create_client(url, key)


def verify_candidate(candidate_id: UUID, organization_id: UUID):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select id from public.candidates where id=%s and organization_id=%s",
                [candidate_id, organization_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Candidate not found")


def safe_filename(filename: str | None, extension: str) -> str:
    raw = Path(filename or "resume" + extension).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw).strip(" .")
    if not cleaned:
        cleaned = "resume" + extension
    if not cleaned.lower().endswith(extension):
        cleaned = Path(cleaned).stem + extension
    return cleaned[:180]


@router.post("", status_code=201, response_model=DocumentOut)
async def upload_candidate_document(
    organization_id: UUID,
    candidate_id: UUID,
    file: UploadFile = File(...),
    application_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    verify_candidate(candidate_id, organization_id)

    mime = (file.content_type or "").lower()
    if mime not in ALLOWED:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported")

    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="CV files must be 5 MB or smaller")

    extension, signature = ALLOWED[mime]
    if not data.startswith(signature):
        raise HTTPException(status_code=415, detail="The file contents do not match the selected file type")

    if application_id:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id from public.applications
                       where id=%s and organization_id=%s and candidate_id=%s""",
                    [application_id, organization_id, candidate_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Application not found for this candidate")

    document_id = uuid4()
    path = f"{organization_id}/{candidate_id}/{document_id}{extension}"
    filename = safe_filename(file.filename, extension)
    digest = hashlib.sha256(data).hexdigest()

    try:
        storage_client().storage.from_(BUCKET).upload(
            path,
            data,
            {"content-type": mime, "upsert": "false", "cache-control": "0"},
        )
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.candidate_documents
                       (id, organization_id, candidate_id, application_id, document_type,
                        original_filename, storage_bucket, storage_path, content_type,
                        file_size_bytes, sha256, uploaded_by)
                       values (%s,%s,%s,%s,'cv',%s,%s,%s,%s,%s,%s,%s)
                       returning id, organization_id, candidate_id, application_id, document_type,
                                 original_filename, content_type, file_size_bytes, sha256, created_at""",
                    [document_id, organization_id, candidate_id, application_id, filename,
                     BUCKET, path, mime, len(data), digest, user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    "update public.candidates set resume_path=%s, updated_at=now() where id=%s and organization_id=%s",
                    [path, candidate_id, organization_id],
                )
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s,%s,'candidate_document_uploaded','candidate_document',%s,%s::jsonb)""",
                    [organization_id, user_id, document_id,
                     '{"candidate_id":"' + str(candidate_id) + '","document_type":"cv"}'],
                )
                return row
    except HTTPException:
        try:
            storage_client().storage.from_(BUCKET).remove([path])
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            storage_client().storage.from_(BUCKET).remove([path])
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Unable to store the document") from exc


@router.get("", response_model=list[DocumentOut])
async def list_candidate_documents(
    organization_id: UUID,
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    verify_candidate(candidate_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, candidate_id, application_id, document_type,
                              original_filename, content_type, file_size_bytes, sha256, created_at
                       from public.candidate_documents
                       where organization_id=%s and candidate_id=%s and deleted_at is null
                       order by created_at desc""",
                    [organization_id, candidate_id],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Document service unavailable") from exc


@router.post("/{document_id}/download")
async def create_document_download(
    document_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select storage_bucket, storage_path, original_filename
                       from public.candidate_documents
                       where id=%s and organization_id=%s and deleted_at is null""",
                    [document_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Document not found")
        result = storage_client().storage.from_(row["storage_bucket"]).create_signed_url(row["storage_path"], 60)
        signed_url = result.get("signedURL") or result.get("signedUrl")
        if not signed_url:
            raise HTTPException(status_code=503, detail="Unable to create secure download link")
        return {"url": signed_url, "filename": row["original_filename"], "expires_in": 60}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Document service unavailable") from exc
