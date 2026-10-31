import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from uuid import uuid4
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, ValidationError
from supabase import create_client

from app.auth import get_current_user_id, get_org_role
from app.db import get_connection

router = APIRouter(tags=["recruitment documents"])
DOCUMENT_MANAGER_ROLES = {"owner", "admin", "recruiter", "hiring_manager"}


def require_document_manager_role(role: str) -> None:
    if role not in DOCUMENT_MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Recruiter or hiring-manager access required")


def require_document_manager(user_id: UUID, organization_id: UUID) -> None:
    require_document_manager_role(get_org_role(user_id, organization_id))
TEMPLATE_PLACEHOLDERS = {
    "candidate.first_name", "candidate.last_name", "candidate.email",
    "job.title", "job.location", "organization.name",
    "offer.title", "offer.employment_type", "offer.start_date",
    "offer.salary_amount", "offer.salary_currency", "offer.benefits",
    "document.date",
}
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")


class TemplateCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=2, max_length=160)
    document_type: Literal["offer_letter", "acknowledgement", "policy", "other"]
    jurisdiction_code: Literal["GB", "US", "IN", "AU", "GLOBAL"]
    body: str = Field(min_length=1, max_length=500000)


class TemplateVersionCreate(BaseModel):
    body: str = Field(min_length=1, max_length=500000)


class SignatureProviderEvent(BaseModel):
    provider: str = Field(min_length=2, max_length=80)
    event_id: str = Field(min_length=1, max_length=255)
    event_type: Literal["sent", "viewed", "signed", "declined", "expired", "revoked"]
    document_id: UUID
    signer_email: str = Field(min_length=3, max_length=320)
    occurred_at: datetime | None = None


def verify_adapter_signature(raw: bytes, timestamp_header: str, signature_header: str, secret: str, now: int | None = None) -> bool:
    try:
        timestamp = int(timestamp_header)
    except (TypeError, ValueError):
        return False
    current_time = int(time.time()) if now is None else now
    if abs(current_time - timestamp) > 300:
        return False
    signed_payload = timestamp_header.encode("ascii") + b"." + raw
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    supplied = signature_header.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, supplied)


def _template_body(body: str) -> tuple[list[str], str]:
    names = sorted(set(PLACEHOLDER_PATTERN.findall(body)))
    unknown = sorted(set(names) - TEMPLATE_PLACEHOLDERS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "Template contains unsupported placeholders", "placeholders": unknown},
        )
    # Reject malformed placeholder-looking tokens instead of silently emitting them.
    stripped = PLACEHOLDER_PATTERN.sub("", body)
    if "{{" in stripped or "}}" in stripped:
        raise HTTPException(status_code=422, detail="Malformed template placeholder")
    return names, hashlib.sha256(body.encode("utf-8")).hexdigest()


@router.get("/api/recruitment-document-templates")
def list_recruitment_document_templates(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    require_document_manager(user_id, organization_id)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """select t.id, t.organization_id, t.name, t.document_type, t.jurisdiction_code,
                      t.current_version, t.active, t.created_by, t.created_at, t.updated_at,
                      v.id as current_version_id, v.content_sha256, v.placeholders, v.created_at as version_created_at
               from public.recruitment_document_templates t
               left join public.recruitment_document_template_versions v
                 on v.template_id=t.id and v.organization_id=t.organization_id and v.version=t.current_version
               where t.organization_id=%s
               order by t.updated_at desc""",
            [organization_id],
        )
        return list(cursor.fetchall())


@router.post("/api/recruitment-document-templates", status_code=status.HTTP_201_CREATED)
def create_recruitment_document_template(
    payload: TemplateCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    require_document_manager(user_id, payload.organization_id)
    placeholders, digest = _template_body(payload.body)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """insert into public.recruitment_document_templates
                 (organization_id,name,document_type,jurisdiction_code,current_version,created_by)
               values (%s,%s,%s,%s,1,%s)
               returning id, organization_id, name, document_type, jurisdiction_code,
                         current_version, active, created_by, created_at, updated_at""",
            [payload.organization_id, payload.name.strip(), payload.document_type,
             payload.jurisdiction_code, user_id],
        )
        template = cursor.fetchone()
        cursor.execute(
            """insert into public.recruitment_document_template_versions
                 (organization_id,template_id,version,body,placeholders,content_sha256,created_by)
               values (%s,%s,1,%s,%s::jsonb,%s,%s)
               returning id, version, placeholders, content_sha256, created_at""",
            [payload.organization_id, template["id"], payload.body, json.dumps(placeholders), digest, user_id],
        )
        version = cursor.fetchone()
        cursor.execute(
            """insert into public.audit_events
                 (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
               values (%s,%s,'recruitment_document_template_created','recruitment_document_template',%s,%s::jsonb)""",
            [payload.organization_id, user_id, template["id"],
             json.dumps({"template_version": 1, "content_sha256": digest})],
        )
        connection.commit()
        return {"template": template, "version": version}


@router.post("/api/recruitment-document-templates/{template_id}/versions", status_code=status.HTTP_201_CREATED)
def create_recruitment_document_template_version(
    template_id: UUID,
    organization_id: UUID,
    payload: TemplateVersionCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    require_document_manager(user_id, organization_id)
    placeholders, digest = _template_body(payload.body)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """select current_version, active from public.recruitment_document_templates
               where id=%s and organization_id=%s for update""",
            [template_id, organization_id],
        )
        template = cursor.fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        if not template["active"]:
            raise HTTPException(status_code=409, detail="Inactive templates cannot be revised")
        next_version = int(template["current_version"]) + 1
        cursor.execute(
            """insert into public.recruitment_document_template_versions
                 (organization_id,template_id,version,body,placeholders,content_sha256,created_by)
               values (%s,%s,%s,%s,%s::jsonb,%s,%s)
               returning id, version, placeholders, content_sha256, created_at""",
            [organization_id, template_id, next_version, payload.body, json.dumps(placeholders), digest, user_id],
        )
        version = cursor.fetchone()
        cursor.execute(
            """update public.recruitment_document_templates
               set current_version=%s, updated_at=now()
               where id=%s and organization_id=%s""",
            [next_version, template_id, organization_id],
        )
        cursor.execute(
            """insert into public.audit_events
                 (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
               values (%s,%s,'recruitment_document_template_version_created','recruitment_document_template',%s,%s::jsonb)""",
            [organization_id, user_id, template_id,
             json.dumps({"template_version": next_version, "content_sha256": digest})],
        )
        connection.commit()
        return version


@router.post("/api/recruitment-signature-events", status_code=status.HTTP_202_ACCEPTED)
async def receive_normalized_signature_event(
    request: Request,
    x_aqerith_timestamp: str = Header(default=""),
    x_aqerith_signature: str = Header(default=""),
):
    """Receive events from a trusted provider adapter after its native webhook verification.

    This is an internal adapter contract, not a claim that provider-native webhook
    verification is implemented. The adapter must sign timestamp + '.' + raw body
    with the AQERITH shared secret. Configure SIGNATURE_WEBHOOK_SECRET only after
    deploying and validating a provider-specific adapter.
    """
    secret = os.getenv("SIGNATURE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Signature event adapter is not configured")
    raw = await request.body()
    if not verify_adapter_signature(raw, x_aqerith_timestamp, x_aqerith_signature, secret):
        raise HTTPException(status_code=401, detail="Invalid or expired webhook signature")

    try:
        event = SignatureProviderEvent.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid normalized signature event") from exc

    digest = hashlib.sha256(raw).hexdigest()
    occurred_at = event.occurred_at
    if occurred_at is not None and occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """select id, organization_id, status from public.recruitment_documents
               where id=%s""",
            [event.document_id],
        )
        document = cursor.fetchone()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        org_id = document["organization_id"]
        cursor.execute(
            """select id, status from public.recruitment_document_signers
               where document_id=%s and organization_id=%s and lower(email)=lower(%s)
               for update""",
            [event.document_id, org_id, event.signer_email],
        )
        signer = cursor.fetchone()
        if signer is None:
            raise HTTPException(status_code=404, detail="Signer not found for this document")

        try:
            cursor.execute(
                """insert into public.recruitment_signature_events
                     (organization_id,document_id,signer_id,provider,provider_event_id,event_type,
                      provider_event_at,payload_sha256,verification_method)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,'aqerith_adapter_hmac_sha256')""",
                [org_id, event.document_id, signer["id"], event.provider, event.event_id,
                 event.event_type, occurred_at, digest],
            )
        except Exception as exc:
            # Unique(provider, provider_event_id) rejects provider retries/replays.
            if "unique" in str(exc).lower() or getattr(exc, "sqlstate", None) == "23505":
                raise HTTPException(status_code=409, detail="Duplicate provider event rejected") from exc
            raise

        signer_status = event.event_type
        stamp_column = {
            "sent": "sent_at", "viewed": "viewed_at", "signed": "signed_at",
            "declined": "declined_at",
        }.get(signer_status)
        assignments = ["status=%s"]
        values: list[object] = [signer_status]
        if stamp_column:
            assignments.append(f"{stamp_column}=coalesce({stamp_column},%s)")
            values.append(occurred_at or datetime.now(timezone.utc))
        values.extend([signer["id"], org_id])
        cursor.execute(
            f"update public.recruitment_document_signers set {', '.join(assignments)} where id=%s and organization_id=%s",
            values,
        )

        # A document is signed only after every signer has signed. Decline/expiry/revocation
        # are terminal states; provider events cannot silently resurrect them.
        if document["status"] not in {"signed", "declined", "expired", "revoked", "void"}:
            if event.event_type in {"declined", "expired", "revoked"}:
                doc_status = event.event_type
            elif event.event_type == "signed":
                cursor.execute(
                    """select count(*) as pending from public.recruitment_document_signers
                       where document_id=%s and organization_id=%s and status <> 'signed'""",
                    [event.document_id, org_id],
                )
                doc_status = "signed" if cursor.fetchone()["pending"] == 0 else document["status"]
            elif event.event_type in {"sent", "viewed"}:
                doc_status = (
                    "sent" if event.event_type == "sent" and document["status"] not in {"viewed", "signed"}
                    else "viewed" if event.event_type == "viewed" and document["status"] in {"sent", "viewed"}
                    else document["status"]
                )
            else:
                doc_status = document["status"]
            if doc_status != document["status"]:
                cursor.execute(
                    """update public.recruitment_documents
                       set status=%s,
                           sent_at=case when %s='sent' then coalesce(sent_at,%s) else sent_at end,
                           viewed_at=case when %s='viewed' then coalesce(viewed_at,%s) else viewed_at end,
                           signed_at=case when %s='signed' then coalesce(signed_at,%s) else signed_at end,
                           declined_at=case when %s='declined' then coalesce(declined_at,%s) else declined_at end,
                           revoked_at=case when %s='revoked' then coalesce(revoked_at,%s) else revoked_at end,
                           updated_at=now()
                       where id=%s and organization_id=%s""",
                    [doc_status,
                     doc_status, occurred_at or datetime.now(timezone.utc),
                     doc_status, occurred_at or datetime.now(timezone.utc),
                     doc_status, occurred_at or datetime.now(timezone.utc),
                     doc_status, occurred_at or datetime.now(timezone.utc),
                     doc_status, occurred_at or datetime.now(timezone.utc),
                     event.document_id, org_id],
                )
        cursor.execute(
            """insert into public.audit_events
                 (organization_id,action,entity_type,entity_id,metadata)
               values (%s,'recruitment_signature_event_verified','recruitment_document',%s,%s::jsonb)""",
            [org_id, event.document_id,
             json.dumps({"provider": event.provider, "event_type": event.event_type,
                         "provider_event_id": event.event_id, "payload_sha256": digest})],
        )
        connection.commit()
        return {"accepted": True, "event_id": event.event_id}


RECRUITMENT_BUCKET = "recruitment-documents"
MAX_RECRUITMENT_DOCUMENT_BYTES = 20 * 1024 * 1024
RECRUITMENT_FILE_TYPES = {
    "application/pdf": (".pdf", b"%PDF-"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx", b"PK\x03\x04"),
}


def _recruitment_storage_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Private recruitment document storage is not configured")
    return create_client(url, key)


def _validate_recruitment_file(data: bytes, mime: str) -> str:
    if mime not in RECRUITMENT_FILE_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX recruitment documents are supported")
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded document is empty")
    if len(data) > MAX_RECRUITMENT_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Recruitment documents must be 20 MB or smaller")
    extension, signature = RECRUITMENT_FILE_TYPES[mime]
    if not data.startswith(signature):
        raise HTTPException(status_code=415, detail="File contents do not match the selected file type")
    return extension


def _safe_recruitment_filename(filename: str | None, extension: str) -> str:
    raw = Path(filename or ("document" + extension)).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw).strip(" .")
    if not cleaned:
        cleaned = "document" + extension
    if not cleaned.lower().endswith(extension):
        cleaned = Path(cleaned).stem + extension
    return cleaned[:180]


def _verify_document_parents(
    organization_id: UUID,
    candidate_id: UUID | None,
    application_id: UUID | None,
    offer_id: UUID | None,
):
    with get_connection() as connection, connection.cursor() as cursor:
        if candidate_id:
            cursor.execute(
                "select id from public.candidates where id=%s and organization_id=%s",
                [candidate_id, organization_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Candidate not found")
        if application_id:
            cursor.execute(
                "select id, candidate_id from public.applications where id=%s and organization_id=%s",
                [application_id, organization_id],
            )
            application = cursor.fetchone()
            if application is None:
                raise HTTPException(status_code=404, detail="Application not found")
            if candidate_id and application["candidate_id"] != candidate_id:
                raise HTTPException(status_code=422, detail="Application does not belong to the selected candidate")
        if offer_id:
            cursor.execute(
                "select id, application_id from public.offers where id=%s and organization_id=%s",
                [offer_id, organization_id],
            )
            offer = cursor.fetchone()
            if offer is None:
                raise HTTPException(status_code=404, detail="Offer not found")
            if application_id and offer["application_id"] != application_id:
                raise HTTPException(status_code=422, detail="Offer does not belong to the selected application")
            if candidate_id and not application_id:
                cursor.execute(
                    "select candidate_id from public.applications where id=%s and organization_id=%s",
                    [offer["application_id"], organization_id],
                )
                linked = cursor.fetchone()
                if linked is None or linked["candidate_id"] != candidate_id:
                    raise HTTPException(status_code=422, detail="Offer does not belong to the selected candidate")


@router.get("/api/recruitment-documents")
def list_recruitment_documents(
    organization_id: UUID,
    candidate_id: UUID | None = None,
    application_id: UUID | None = None,
    offer_id: UUID | None = None,
    user_id: UUID = Depends(get_current_user_id),
):
    require_document_manager(user_id, organization_id)
    _verify_document_parents(organization_id, candidate_id, application_id, offer_id)
    filters = ["organization_id=%s"]
    values: list[object] = [organization_id]
    for column, value in (("candidate_id", candidate_id), ("application_id", application_id), ("offer_id", offer_id)):
        if value is not None:
            filters.append(f"{column}=%s")
            values.append(value)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """select id, organization_id, document_group_id, version, template_version_id,
                      candidate_id, application_id, offer_id, document_type, jurisdiction_code,
                      status, file_name, content_type, file_size_bytes, content_sha256,
                      generated_from_template_version, sent_at, viewed_at, signed_at,
                      declined_at, expires_at, revoked_at, created_by, created_at, updated_at
               from public.recruitment_documents where """ + " and ".join(filters) + " order by created_at desc",
            values,
        )
        return list(cursor.fetchall())


@router.post("/api/recruitment-documents", status_code=status.HTTP_201_CREATED)
async def store_recruitment_document(
    organization_id: UUID,
    document_type: Literal["offer_letter", "acknowledgement", "policy", "other"],
    jurisdiction_code: Literal["GB", "US", "IN", "AU", "GLOBAL"],
    file: UploadFile = File(...),
    candidate_id: UUID | None = Query(default=None),
    application_id: UUID | None = Query(default=None),
    offer_id: UUID | None = Query(default=None),
    template_version_id: UUID | None = Query(default=None),
    document_group_id: UUID | None = Query(default=None),
    generated_from_template_version: int | None = Query(default=None, ge=1),
    user_id: UUID = Depends(get_current_user_id),
):
    """Store a generated or approved recruitment document as a new immutable version.

    This endpoint stores supplied PDF/DOCX bytes; it does not itself render template
    placeholders into a PDF. The rendering pipeline must pass its generated artifact here.
    """
    require_document_manager(user_id, organization_id)
    if not any((candidate_id, application_id, offer_id)):
        raise HTTPException(status_code=422, detail="A candidate, application, or offer must be linked")
    _verify_document_parents(organization_id, candidate_id, application_id, offer_id)

    if template_version_id:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """select id from public.recruitment_document_template_versions
                   where id=%s and organization_id=%s""",
                [template_version_id, organization_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Template version not found")

    mime = (file.content_type or "").lower()
    data = await file.read(MAX_RECRUITMENT_DOCUMENT_BYTES + 1)
    extension = _validate_recruitment_file(data, mime)
    digest = hashlib.sha256(data).hexdigest()
    document_id = uuid4()
    group_id = document_group_id or uuid4()
    filename = _safe_recruitment_filename(file.filename, extension)
    version = 1

    with get_connection() as connection, connection.cursor() as cursor:
        if document_group_id:
            cursor.execute(
                """select version, candidate_id, application_id, offer_id, document_type, jurisdiction_code
                   from public.recruitment_documents
                   where document_group_id=%s and organization_id=%s
                   order by version desc limit 1""",
                [document_group_id, organization_id],
            )
            latest = cursor.fetchone()
            if latest is None:
                raise HTTPException(status_code=404, detail="Document version group not found")
            if (latest["candidate_id"], latest["application_id"], latest["offer_id"], latest["document_type"], latest["jurisdiction_code"]) != (candidate_id, application_id, offer_id, document_type, jurisdiction_code):
                raise HTTPException(status_code=422, detail="A new version must preserve the original document's parent records and classification")
            version = int(latest["version"]) + 1

    storage_path = f"{organization_id}/{group_id}/v{version}/{document_id}{extension}"
    storage = _recruitment_storage_client()
    try:
        storage.storage.from_(RECRUITMENT_BUCKET).upload(
            storage_path, data,
            {"content-type": mime, "upsert": "false", "cache-control": "0"},
        )
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """insert into public.recruitment_documents
                     (id,organization_id,document_group_id,version,template_version_id,
                      candidate_id,application_id,offer_id,document_type,jurisdiction_code,status,
                      storage_bucket,storage_path,file_name,content_type,file_size_bytes,content_sha256,
                      generated_from_template_version,created_by)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'generated',%s,%s,%s,%s,%s,%s,%s,%s)
                   returning id, organization_id, document_group_id, version, status, file_name,
                             content_type, file_size_bytes, content_sha256, created_at""",
                [document_id, organization_id, group_id, version, template_version_id,
                 candidate_id, application_id, offer_id, document_type, jurisdiction_code,
                 RECRUITMENT_BUCKET, storage_path, filename, mime, len(data), digest,
                 generated_from_template_version, user_id],
            )
            row = cursor.fetchone()
            cursor.execute(
                """insert into public.audit_events
                     (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                   values (%s,%s,'recruitment_document_version_created','recruitment_document',%s,%s::jsonb)""",
                [organization_id, user_id, document_id,
                 json.dumps({"document_group_id": str(group_id), "version": version, "content_sha256": digest})],
            )
            connection.commit()
            return row
    except Exception as exc:
        try:
            storage.storage.from_(RECRUITMENT_BUCKET).remove([storage_path])
        except Exception:
            pass
        if isinstance(exc, HTTPException):
            raise
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="A concurrent version was created; retry with the latest version") from exc
        raise HTTPException(status_code=503, detail="Unable to store the recruitment document") from exc


@router.post("/api/recruitment-documents/{document_id}/download")
def create_recruitment_document_download(
    document_id: UUID,
    organization_id: UUID,
    preview: bool = Query(default=False),
    user_id: UUID = Depends(get_current_user_id),
):
    require_document_manager(user_id, organization_id)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """select storage_bucket, storage_path, file_name, status
               from public.recruitment_documents
               where id=%s and organization_id=%s""",
            [document_id, organization_id],
        )
        document = cursor.fetchone()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if document["status"] in {"expired", "revoked", "void"}:
            raise HTTPException(status_code=410, detail="This document is no longer available")
        action = "preview" if preview else "download"
        cursor.execute(
            """insert into public.recruitment_document_access_events
                 (organization_id,document_id,actor_user_id,action,metadata)
               values (%s,%s,%s,%s,%s::jsonb)""",
            [organization_id, document_id, user_id, action, json.dumps({"source": "authenticated_api"})],
        )
        connection.commit()
    try:
        result = _recruitment_storage_client().storage.from_(document["storage_bucket"]).create_signed_url(
            document["storage_path"], 60
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Unable to create a short-lived document link") from exc
    signed_url = result.get("signedURL") or result.get("signedUrl")
    if not signed_url:
        raise HTTPException(status_code=503, detail="Storage did not return a document link")
    return {"url": signed_url, "expires_in_seconds": 60, "file_name": document["file_name"], "preview": preview}
