import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(tags=["recruitment documents"])
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
    assert_org_member(user_id, organization_id)
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
    assert_org_member(user_id, payload.organization_id)
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
    assert_org_member(user_id, organization_id)
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
    try:
        timestamp = int(x_aqerith_timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid webhook timestamp") from exc
    if abs(int(time.time()) - timestamp) > 300:
        raise HTTPException(status_code=401, detail="Webhook timestamp outside allowed window")

    raw = await request.body()
    signed_payload = x_aqerith_timestamp.encode("ascii") + b"." + raw
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    supplied = x_aqerith_signature.removeprefix("sha256=").strip().lower()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

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
                doc_status = event.event_type if event.event_type == "sent" or document["status"] == "sent" else document["status"]
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
