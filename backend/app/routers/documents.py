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
    extracted_profile: dict | None = None


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
    extracted_text = extract_cv_text(data, mime)
    extracted_profile = extract_cv_profile(extracted_text, filename)

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
                return {**row, "extracted_profile": extracted_profile}
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
        result = storage_client().storage.from_(row["storage_bucket"]).create_signed_url(row["storage_path"], 60, options={"download": row["original_filename"]})
        signed_url = result.get("signedURL") or result.get("signedUrl")
        if not signed_url:
            raise HTTPException(status_code=503, detail="Unable to create secure download link")
        return {"url": signed_url, "filename": row["original_filename"], "expires_in": 60}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Document service unavailable") from exc


@router.post("/{document_id}/extract")
async def reextract_candidate_document(
    document_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Re-run CV text extraction for an already uploaded document without changing candidate data."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select candidate_id, storage_bucket, storage_path, content_type, original_filename
                       from public.candidate_documents
                       where id=%s and organization_id=%s and deleted_at is null and document_type='cv'""",
                    [document_id, organization_id],
                )
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="CV document not found")
        candidate_id = row["candidate_id"]
        verify_candidate(candidate_id, organization_id)
        data = storage_client().storage.from_(row["storage_bucket"]).download(row["storage_path"])
        text = extract_cv_text(data, row["content_type"])
        profile = extract_cv_profile(text, row["original_filename"])
        return {"filename": row["original_filename"], "candidate_id": str(candidate_id), "extracted_profile": profile}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("CV re-extraction failed for document %s", document_id)
        raise HTTPException(status_code=503, detail="Could not re-extract this CV. Check document storage and try again.") from exc


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
    "hadoop", "snowflake", "dbt", "oracle", "oracle e-business suite", "etl",
    "data warehousing", "data engineering", "data modeling", "data modelling",
    "apache spark", "spark", "airflow", "databricks", "redshift", "bigquery",
    "financial applications", "business intelligence", "data governance",
    "data quality", "aws cloud", "oracle ebs", "pl/sql", "linux", "git",
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


def _cv_sections(text: str) -> dict:
    """Conservative, review-first section extraction for common CV layouts."""
    raw_lines = [re.sub(r"\s+", " ", line).strip(" \t|•-") for line in text.splitlines()]
    raw_lines = [line for line in raw_lines if line]
    headings = {
        "employment": re.compile(r"^(work experience|professional experience|employment history|experience|career history)$", re.I),
        "education": re.compile(r"^(education|academic background|qualifications|academic qualifications)$", re.I),
        "certifications": re.compile(r"^(certifications|certificates|licenses|licences|professional certifications)$", re.I),
        "languages": re.compile(r"^(languages|language skills)$", re.I),
        "skills": re.compile(r"^(skills|technical skills|core competencies|key skills|technologies)$", re.I),
    }
    sections: dict[str, list[str]] = {key: [] for key in headings}
    current = None
    for line in raw_lines:
        matched = next((key for key, pattern in headings.items() if pattern.fullmatch(line.rstrip(":"))), None)
        if matched:
            current = matched
            continue
        if current and re.fullmatch(r"(projects|references|interests|hobbies|personal statement|summary|profile|contact details|achievements|publications|volunteering)", line, re.I):
            current = None
        elif current:
            sections[current].append(line)

    def date_range(line: str):
        match = re.search(
            r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(19\d{2}|20\d{2})\s*(?:-|–|—|to)\s*(Present|Current|Now|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19\d{2}|20\d{2}))\b",
            line, re.I
        )
        if not match:
            return None, None, False
        def iso(value):
            if not value:
                return None
            years = re.search(r"(19\d{2}|20\d{2})", value)
            if not years:
                return None
            month_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*", value, re.I)
            months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"sept":9,"oct":10,"nov":11,"dec":12}
            month = months.get(month_match.group(1).lower()) if month_match else 1
            return f"{years.group(1)}-{month:02d}-01"
        start = (match.group(1) or "") + match.group(2)
        end = match.group(3)
        is_current = end.lower() in {"present", "current", "now"}
        return iso(start), None if is_current else iso(end), is_current

    employment = []
    # Recognise common "Title at Company", "Title | Company", and stacked title/company lines.
    exp = sections["employment"]
    title_pattern = re.compile(r"(?i)\b(?:senior|junior|lead|principal|staff|assistant|associate|head of\s+)?(?:software|full[ -]?stack|data|python|java|project|program|operations|marketing|recruitment|business|product|customer success|finance|sales|HR|human resources)?\s*(?:developer|engineer|analyst|architect|consultant|designer|manager|recruiter|scientist|coordinator|administrator|specialist|director|officer|executive|technician|accountant|intern)\b")
    role_header_indices = []
    for index, candidate_line in enumerate(exp):
        candidate_clean = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:Present|Current|Now|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2})\b", "", candidate_line, flags=re.I).strip(" ,|–—-")
        if title_pattern.search(candidate_clean) and any(sep in candidate_clean for sep in (" | ", " — ", " – ", " - ")) and len(candidate_clean.split()) <= 12:
            role_header_indices.append(index)
    for i, line in enumerate(exp):
        if len(employment) >= 15:
            break
        start_date, end_date, current_role = date_range(line)
        if not start_date:
            for nearby in exp[i + 1:i + 4]:
                nearby_start, nearby_end, nearby_current = date_range(nearby)
                if nearby_start:
                    start_date, end_date, current_role = nearby_start, nearby_end, nearby_current
                    break
        cleaned = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:Present|Current|Now|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2})\b", "", line, flags=re.I).strip(" ,|–—-")
        title_match = title_pattern.search(cleaned)
        title = title_match.group(0).strip() if title_match else ""
        company = ""
        if title and re.search(r"\s(?:at|@)\s", cleaned, re.I):
            company = re.split(r"\s(?:at|@)\s", cleaned, maxsplit=1, flags=re.I)[-1].strip(" ,|")
        elif title and any(sep in cleaned for sep in (" | ", " — ", " – ", " - ")):
            parts = re.split(r"\s(?:\||—|–|-)\s", cleaned)
            if len(parts) >= 2:
                title = parts[0].strip() if title_match.start() < len(parts[0]) else title
                company = parts[1].strip()
        elif title and i + 1 < len(exp):
            next_line = exp[i + 1]
            if len(next_line) <= 100 and not date_range(next_line)[0] and not re.search(r"(?i)\b(?:developer|engineer|analyst|manager|coordinator|consultant|intern)\b", next_line):
                company = next_line
        if title and company and len(company) <= 200:
            description_lines = []
            next_role_index = next((idx for idx in role_header_indices if idx > i), None)
            description_end = min(i + 5, next_role_index) if next_role_index is not None else min(i + 5, len(exp))
            # When multiple roles are listed as a cluster, bullets after the final role are
            # ambiguous shared responsibilities. Do not attribute them to the final employer.
            has_previous_role = any(idx < i for idx in role_header_indices)
            final_role_in_cluster = has_previous_role and next_role_index is None
            if not final_role_in_cluster:
                for following in exp[i + 1:description_end]:
                    if following != company and following != line and not date_range(following)[0]:
                        description_lines.append(following)
            employment.append({
                "job_title": title[:200], "employer_name": company[:200],
                "location": None, "employment_type": None, "start_date": start_date,
                "end_date": end_date, "is_current": current_role,
                "description": " ".join(description_lines)[:1500] or None,
            })
    education = []
    edu = sections["education"]
    qualification_pattern = re.compile(r"(?i)\b(Bachelor(?:'s)?|Master(?:'s)?|Ph\.?D\.?|Doctorate|B\.?Sc\.?|M\.?Sc\.?|B\.?Eng\.?|M\.?Eng\.?|B\.?Tech|M\.?Tech|MBA|Diploma|GCSE|A-level|degree)\b")
    for i, line in enumerate(edu):
        if len(education) >= 10:
            break
        qualification_match = qualification_pattern.search(line)
        if not qualification_match:
            continue
        institution = ""
        qualification_line = line
        # CVs commonly put the institution on the line before the qualification.
        if " | " in line or " — " in line or " - " in line:
            parts = re.split(r"\s(?:\||—|-)\s", line)
            if len(parts) > 1:
                left, right = parts[0].strip(), parts[1].strip()
                if qualification_pattern.search(left):
                    qualification_line, institution = left, right
                elif qualification_pattern.search(right):
                    qualification_line, institution = right, left
        if not institution and i > 0:
            previous = edu[i - 1]
            if not date_range(previous)[0] and not qualification_pattern.search(previous) and len(previous) <= 200:
                institution = previous
        if not institution and i + 1 < len(edu):
            following = edu[i + 1]
            if not date_range(following)[0] and not qualification_pattern.search(following):
                institution = following
        if institution and len(institution) <= 200:
            start_date, end_date, _ = date_range(line)
            if not start_date:
                for nearby in edu[max(0, i - 1):i + 3]:
                    nearby_start, nearby_end, _ = date_range(nearby)
                    if nearby_start:
                        start_date, end_date = nearby_start, nearby_end
                        break
            qualification = re.sub(
                r"\s*((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2})\s*$",
                "", qualification_line, flags=re.I,
            ).strip(" ,|–—-")
            education.append({
                "institution_name": institution[:200], "qualification": (qualification or qualification_line)[:200],
                "field_of_study": None, "start_date": start_date, "end_date": end_date,
                "grade": None, "description": None,
            })
    certifications = []
    for line in sections["certifications"][:20]:
        name = re.sub(r"^[•*\-]\s*", "", line).strip()
        if len(name) >= 3 and not re.fullmatch(r"\d{4}", name):
            certifications.append({"name": name[:200], "issuing_organisation": None, "credential_id": None, "credential_url": None, "issued_on": None, "expires_on": None})
    languages = []
    language_names = ("English", "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Bengali", "Punjabi", "Gujarati", "Marathi", "Urdu", "Spanish", "French", "German", "Arabic", "Mandarin", "Chinese", "Japanese", "Portuguese", "Italian", "Dutch")
    for line in sections["languages"]:
        for language in language_names:
            if re.search(r"(?<![A-Za-z])" + re.escape(language) + r"(?![A-Za-z])", line, re.I):
                proficiency = None
                for label, value in (("native", "native"), ("fluent", "fluent"), ("professional", "professional"), ("conversational", "conversational"), ("basic", "basic")):
                    if re.search(r"\b" + label + r"\b", line, re.I):
                        proficiency = value
                        break
                if not any(item["language"].lower() == language.lower() for item in languages):
                    languages.append({"language": language, "proficiency": proficiency})
    return {"employment": employment, "education": education, "certifications": certifications, "languages": languages}


def extract_cv_profile(text: str, filename: str) -> dict:
    """Extract reviewable profile suggestions from selectable CV text."""
    # For profile suggestions, never infer a person's name from the uploaded filename.
    # Keep filename-based naming only for the separate bulk-import workflow.
    fields = cv_candidate_fields(text, filename, use_filename_fallback=False)
    if not text.strip():
        fields.update({"first_name": "", "last_name": None, "email": None, "phone": None, "skills": []})
    lines = [re.sub(r"\s+", " ", line).strip(" \t|•-") for line in text.splitlines()]
    role_pattern = re.compile(
        r"(?i)\b(?:(?:senior|junior|lead|principal|staff)\s+)?"
        r"(?:(?:software|full[ -]?stack|java|python|data|machine learning|cloud|devops|program|project|"
        r"operations|marketing|recruitment|hr|human resources|business|product|customer success|finance|sales)\s+)?"
        r"(?:developer|engineer|analyst|architect|consultant|designer|manager|recruiter|scientist|"
        r"coordinator|administrator|specialist|director|officer|executive|technician|accountant|teacher|nurse|doctor|researcher|intern|assistant)\b"
    )
    title = None
    for line in lines[:80]:
        if len(line) <= 100:
            match = role_pattern.search(line)
            if match:
                title = match.group(0)[:200]
                break
    links = []
    for raw_url in re.findall(r"https?://[^\s<>]+", text, re.I):
        url = raw_url.rstrip(".,;:)")
        host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url, flags=re.I).split("/")[0], flags=re.I).lower()
        kind = "linkedin" if "linkedin.com" in host else "github" if "github.com" in host else "portfolio"
        if not any(item["url"] == url for item in links):
            links.append({"type": kind, "url": url})
    location = None
    for line in lines[:25]:
        if "@" not in line and "http" not in line.lower():
            match = re.search(
                r"\b([A-Z][A-Za-z .'-]{1,30}),\s*([A-Z][A-Za-z .'-]{1,30})(?:,\s*(United Kingdom|United States of America|United States|Great Britain|England|Scotland|Wales|Northern Ireland|UK|USA|India|Australia|[A-Z]{2}))?\b",
                line,
            )
            if match:
                location = {"city": match.group(1).strip(), "region": match.group(2).strip(), "country": match.group(3)}
                break
    return {**fields, "current_title": title, "location": location, "links": links[:20], **_cv_sections(text), "review_required": True, "ocr_required": not bool(text.strip())}

def cv_candidate_fields(text: str, filename: str, *, use_filename_fallback: bool = True) -> dict:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone_match = re.search(r"(?<!\w)(?:\+?\d[\d ()\-.]{7,}\d)(?!\w)", text)
    excluded = {
        "curriculum vitae", "resume", "résumé", "cv", "professional summary",
        "summary", "profile", "contact", "contact details", "work experience",
        "professional experience", "education", "skills", "experience", "objective",
        "personal statement", "references", "key achievements", "technical skills",
    }
    # A role heading is common near the top of a CV and must never be mistaken for a person's name.
    role_heading = re.compile(
        r"(?i)\b(?:(?:senior|junior|lead|principal|staff|assistant|associate|head of|chief)\s+)?"
        r"(?:(?:software|full[ -]?stack|java|python|data|machine learning|cloud|devops|program|project|"
        r"operations|marketing|recruitment|hr|human resources|business|product|customer success|finance|sales)\s+)?"
        r"(?:developer|engineer|analyst|architect|consultant|designer|manager|recruiter|scientist|"
        r"coordinator|administrator|specialist|director|officer|executive|technician|accountant|teacher|"
        r"nurse|doctor|researcher|intern|assistant|student)\b"
    )
    name = ""
    candidate_lines = text.splitlines()[:15]
    for line_index, raw_line in enumerate(candidate_lines):
        line = re.sub(r"\s+", " ", raw_line).strip(" \t|•-")
        if not line or len(line) > 80 or "@" in line or "http" in line.lower() or re.search(r"\d{3}", line):
            continue
        if line.casefold() in excluded or len(line.split()) > 5 or role_heading.search(line):
            continue
        if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'’. -]+", line):
            if len(line.split()) >= 2:
                name = line
                break
            # Some CVs use a single-word name; accept it only at the very top when contact details follow.
            nearby = " ".join(candidate_lines[line_index + 1:line_index + 4])
            if line_index <= 2 and (email_match or phone_match) and len(line) >= 2:
                name = line
                break
    if not name and use_filename_fallback:
        stem = Path(filename).stem
        stem = re.sub(r"\b(cv|resume|résumé|curriculum vitae|final|updated|new)\b", " ", stem, flags=re.I)
        stem = re.sub(r"[_-]+", " ", stem)
        name = re.sub(r"\s+", " ", stem).strip(" .-_")
    parts = name.split()
    first_name = (parts[0] if parts else ("CV candidate" if use_filename_fallback else ""))[:100]
    last_name = (" ".join(parts[1:]) if len(parts) > 1 else None)
    skills = [skill for skill in CV_SKILL_KEYWORDS if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", text, re.I)]
    return {
        "first_name": first_name,
        "last_name": last_name[:100] if last_name else None,
        "email": email_match.group(0).lower() if email_match else None,
        "phone": re.sub(r"\s+", " ", phone_match.group(0)).strip()[:50] if phone_match else None,
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
                               (id, organization_id, first_name, last_name, email, phone, status,
                                skills, resume_path, resume_text, created_at, updated_at)
                               values (%s,%s,%s,%s,%s,%s,'active',%s,%s,%s,now(),now())""",
                            [candidate_id, organization_id, fields["first_name"], fields["last_name"],
                             fields["email"], fields["phone"], fields["skills"], path, text or None],
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
                    "email": fields["email"], "skills_found": fields["skills"],
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
