import hashlib
import io
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from docx import Document as DocxDocument
from pypdf import PdfReader
from pydantic import BaseModel
from supabase import create_client

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/documents", tags=["candidate documents"])
logger = logging.getLogger(__name__)
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
    created_at: datetime | None = None


def validate_document_bytes(data: bytes, mime: str) -> str:
    """Validate the allowlisted file type, bounded size, and basic file signature."""
    if mime not in ALLOWED:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported")
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="CV files must be 5 MB or smaller")
    extension, signature = ALLOWED[mime]
    if not data.startswith(signature):
        raise HTTPException(status_code=415, detail="The file contents do not match the selected file type")
    return extension


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
    data = await file.read(MAX_BYTES + 1)
    extension = validate_document_bytes(data, mime)

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
    try:
        verify_candidate(candidate_id, organization_id)
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
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        logger.exception("Database failure while listing candidate documents")
        raise HTTPException(status_code=503, detail="Document service unavailable; please retry shortly") from exc
    except Exception as exc:
        logger.exception("Unexpected failure while listing candidate documents")
        raise HTTPException(status_code=503, detail="Unable to load candidate documents; please retry shortly") from exc


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
        result = storage_client().storage.from_(row["storage_bucket"]).create_signed_url(row["storage_path"], 60, options={"download": False})
        signed_url = result.get("signedURL") or result.get("signedUrl")
        if not signed_url:
            raise HTTPException(status_code=503, detail="Unable to create secure download link")
        return {"url": signed_url, "filename": row["original_filename"], "expires_in": 60}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Document service unavailable") from exc


@router.post("/{document_id}/preview")
async def preview_candidate_document(
    document_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Return a short-lived inline PDF URL or extracted DOCX text for an authorised recruiter."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select candidate_id, storage_bucket, storage_path, original_filename, content_type
                       from public.candidate_documents
                       where id=%s and organization_id=%s and deleted_at is null""",
                    [document_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Document not found")
        if row["content_type"] == "application/pdf":
            result = storage_client().storage.from_(row["storage_bucket"]).create_signed_url(
                row["storage_path"], 60, options={"download": False}
            )
            signed_url = result.get("signedURL") or result.get("signedUrl")
            if not signed_url:
                raise HTTPException(status_code=503, detail="Unable to create secure preview link")
            return {"kind": "pdf", "url": signed_url, "filename": row["original_filename"], "expires_in": 60}

        if row["content_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            data = storage_client().storage.from_(row["storage_bucket"]).download(row["storage_path"])
            text = extract_cv_text(data, row["content_type"])
            if not text.strip():
                raise HTTPException(status_code=422, detail="No readable text was found in this DOCX file")
            return {"kind": "text", "text": text, "filename": row["original_filename"]}

        raise HTTPException(status_code=415, detail="Preview is not supported for this file type")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to preview candidate document")
        raise HTTPException(status_code=503, detail="Unable to preview this document right now") from exc


MAX_BULK_FILES = 20
MAX_BULK_BYTES = 4 * 1024 * 1024  # Stay below the Vercel Functions request-body limit.
CV_SKILL_KEYWORDS = (
    "python", "java", "javascript", "typescript", "react", "next.js", "node.js",
    "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker",
    "kubernetes", "machine learning", "deep learning", "tensorflow", "pytorch",
    "data analysis", "power bi", "tableau", "excel", "django", "fastapi",
    "project management", "salesforce", "account management", "recruitment",
)


def extract_cv_text(data: bytes, mime: str) -> str:
    """Extract selectable text from supported CV formats; scanned PDFs need OCR separately."""
    try:
        if mime == "application/pdf":
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages[:20])[:100_000]
        if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            document = DocxDocument(io.BytesIO(data))
            parts = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" ".join(cell.text for cell in row.cells))
            return "\n".join(parts)[:100_000]
    except Exception:
        return ""
    return ""


def cv_candidate_fields(text: str, filename: str) -> dict:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone_match = re.search(r"(?<!\w)(?:\+?\d[\d ()\-.]{7,}\d)(?!\w)", text)
    excluded = {
        "curriculum vitae", "resume", "résumé", "cv", "professional summary",
        "summary", "profile", "contact", "contact details", "work experience",
        "professional experience", "education", "skills", "experience",
        "core skills", "key skills", "technical skills", "soft skills",
        "career summary", "professional summary", "objective", "career objective",
        "personal details", "personal information", "about me", "highlights",
        "certifications", "projects", "languages", "references", "achievements",
    }
    name = ""
    for raw_line in text.splitlines()[:15]:
        line = re.sub(r"\s+", " ", raw_line).strip(" \t|•-")
        if not line or len(line) > 80 or "@" in line or re.search(r"\d{3}", line):
            continue
        if line.casefold().rstrip(":") in excluded or len(line.split()) > 5:
            continue
        # CVs often show a single given name (e.g. "Abhaya") on its own.
        # Accept one-word names only when they look like a name, not a section label.
        if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’. -]*", line):
            words = line.split()
            if len(words) >= 2 or (len(words) == 1 and line[0].isupper() and len(line) >= 3 and line.casefold() not in excluded):
                name = line
                break
    if not name:
        stem = Path(filename).stem
        stem = re.sub(r"\b(cv|resume|résumé|curriculum vitae|final|updated|new)\b", " ", stem, flags=re.I)
        stem = re.sub(r"[_-]+", " ", stem)
        name = re.sub(r"\s+", " ", stem).strip(" .-_")
    parts = name.split()
    first_name = (parts[0] if parts else "CV candidate")[:100]
    last_name = (" ".join(parts[1:]) if len(parts) > 1 else None)
    # Prefer explicitly labelled roles; fallback only to recognisable role titles near the top.
    title = None
    title_patterns = (
        r"^(?:current\s+(?:job\s+)?title|professional title|role|position|designation)\s*[:：-]\s*(.+)$",
        r"^((?:(?:sr\.?|jr\.?|senior|junior|lead|principal|staff|associate|assistant|head of|director of|chief)\s+)?[A-Za-z][A-Za-z /&(),.+-]{2,65}\b(?:engineer|developer|analyst|scientist|manager|consultant|architect|administrator|designer|specialist|recruiter|accountant|coordinator|technician|director|officer|nurse|teacher|researcher|intern)\b.*)$",
    )
    opening_lines = [re.sub(r"\s+", " ", item).strip(" \t|•-") for item in text.splitlines()[:35]]
    for line in opening_lines:
        if not line or len(line) > 90 or "@" in line or line.casefold() in excluded:
            continue
        for pattern in title_patterns:
            match = re.match(pattern, line, re.I)
            if match:
                candidate_title = match.group(1).strip(" .|:-")
                # A CV experience line often combines title, employer, location and dates.
                candidate_title = re.split(r"\s+(?:at|@)\s+|\s{2,}|\s+[|•]\s+", candidate_title, maxsplit=1, flags=re.I)[0]
                candidate_title = re.sub(r"\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}.*$", "", candidate_title, flags=re.I)
                if 3 <= len(candidate_title) <= 100 and candidate_title.casefold() not in excluded:
                    title = candidate_title[:100]
                    break
        if title:
            break

    experience = None
    for pattern in (
        r"(?:total\s+)?(?:work\s+)?experience\s*[:：-]?\s*(\d{1,2}(?:\.\d+)?)\s*\+?\s*years?",
        r"(\d{1,2}(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?experience",
    ):
        match = re.search(pattern, text[:12000], re.I)
        if match:
            value = float(match.group(1))
            if 0 <= value <= 80:
                experience = value
                break

    education = None
    education_heading = re.compile(r"^\s*(education|academic background|qualifications|educational qualifications)\s*[:：]?\s*$", re.I)
    section_heading = re.compile(r"^\s*(work experience|professional experience|employment history|skills|certifications|projects|references|awards|publications)\s*[:：]?\s*$", re.I)
    for index, line in enumerate(text.splitlines()):
        if education_heading.match(line.strip()):
            collected = []
            for candidate_line in text.splitlines()[index + 1:index + 9]:
                clean = re.sub(r"\s+", " ", candidate_line).strip(" \t|•-")
                if section_heading.match(clean):
                    break
                if clean and len(clean) <= 180:
                    collected.append(clean)
            if collected:
                education = " | ".join(collected)[:500]
                break

    skills = [skill for skill in CV_SKILL_KEYWORDS if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", text, re.I)]
    return {
        "first_name": first_name,
        "last_name": last_name[:100] if last_name else None,
        "email": email_match.group(0).lower() if email_match else None,
        "phone": re.sub(r"\s+", " ", phone_match.group(0)).strip()[:50] if phone_match else None,
        "current_title": title,
        "years_experience": experience,
        "education": education,
        "skills": skills[:30],
    }


@router.post("/bulk-cv", status_code=200)
async def bulk_upload_cvs(
    organization_id: UUID,
    files: list[UploadFile] = File(...),
    user_id: UUID = Depends(get_current_user_id),
):
    """Create candidate profiles from a batch of PDF/DOCX CVs and store each CV privately."""
    assert_org_member(user_id, organization_id)
    if not files:
        raise HTTPException(status_code=422, detail="Choose at least one CV to upload")
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(status_code=413, detail=f"Upload up to {MAX_BULK_FILES} CVs per batch")

    declared_total = sum(file.size or 0 for file in files)
    if declared_total > MAX_BULK_BYTES:
        raise HTTPException(status_code=413, detail="The total batch must be 4 MB or smaller. Split larger batches into multiple uploads.")

    results = []
    for file in files:
        filename = Path(file.filename or "resume.pdf").name
        mime = (file.content_type or "").lower()
        data = await file.read(MAX_BYTES + 1)
        try:
            extension = validate_document_bytes(data, mime)
            filename = safe_filename(file.filename, extension)
            digest = hashlib.sha256(data).hexdigest()
            text = extract_cv_text(data, mime)
            fields = cv_candidate_fields(text, filename)
            if not fields["first_name"].strip():
                fields["first_name"] = "CV candidate"

            with get_connection() as connection:
                with connection.cursor() as cursor:
                    if fields["email"]:
                        cursor.execute(
                            "select id from public.candidates where organization_id=%s and lower(email)=lower(%s) limit 1",
                            [organization_id, fields["email"]],
                        )
                        existing = cursor.fetchone()
                        if existing:
                            results.append({"filename": filename, "status": "duplicate", "message": "A candidate with this email already exists", "candidate_id": str(existing["id"])})
                            continue
                    cursor.execute(
                        "select id from public.candidate_documents where organization_id=%s and sha256=%s and deleted_at is null limit 1",
                        [organization_id, digest],
                    )
                    if cursor.fetchone():
                        results.append({"filename": filename, "status": "duplicate", "message": "This CV file has already been uploaded"})
                        continue

            candidate_id = uuid4()
            document_id = uuid4()
            path = f"{organization_id}/{candidate_id}/{document_id}{extension}"
            storage_client().storage.from_(BUCKET).upload(
                path, data, {"content-type": mime, "upsert": "false", "cache-control": "0"}
            )
            try:
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """insert into public.candidates
                               (id, organization_id, first_name, last_name, email, phone, current_title, years_experience, status,
                                skills, resume_path, resume_text, created_at, updated_at)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s,now(),now())""",
                            [candidate_id, organization_id, fields["first_name"], fields["last_name"],
                             fields["email"], fields["phone"], fields["current_title"], fields["years_experience"],
                             fields["skills"], path, text or None],
                        )
                        cursor.execute(
                            """insert into public.candidate_documents
                               (id, organization_id, candidate_id, application_id, document_type,
                                original_filename, storage_bucket, storage_path, content_type,
                                file_size_bytes, sha256, uploaded_by)
                               values (%s,%s,%s,null,'cv',%s,%s,%s,%s,%s,%s,%s)""",
                            [document_id, organization_id, candidate_id, filename, BUCKET, path,
                             mime, len(data), digest, user_id],
                        )
                        cursor.execute(
                            """insert into public.audit_events
                               (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                               values (%s,%s,'candidate_cv_bulk_imported','candidate',%s,%s::jsonb)""",
                            [organization_id, user_id, candidate_id,
                             '{"filename":' + __import__("json").dumps(filename) + ',"document_id":"' + str(document_id) + '"}'],
                        )
                results.append({
                    "filename": filename, "status": "imported", "candidate_id": str(candidate_id),
                    "name": " ".join(part for part in [fields["first_name"], fields["last_name"]] if part),
                    "email": fields["email"], "current_title": fields["current_title"],
                    "years_experience": fields["years_experience"], "education": fields["education"],
                    "skills_found": fields["skills"],
                    "text_extracted": bool(text.strip()),
                })
            except Exception:
                try:
                    storage_client().storage.from_(BUCKET).remove([path])
                except Exception:
                    pass
                raise
        except HTTPException as exc:
            results.append({"filename": filename, "status": "error", "message": str(exc.detail)})
        except Exception:
            results.append({"filename": filename, "status": "error", "message": "Could not import this CV. Check storage/database configuration and try again."})
        finally:
            await file.close()

    return {"total": len(files), "imported": sum(item["status"] == "imported" for item in results),
            "duplicates": sum(item["status"] == "duplicate" for item in results),
            "failed": sum(item["status"] == "error" for item in results), "results": results}
