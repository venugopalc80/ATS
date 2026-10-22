import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

RequestType = Literal["access", "correction", "restriction", "erasure", "portability", "objection", "other"]
RequestStatus = Literal[
    "received", "identity_verification", "in_progress", "awaiting_information",
    "partially_completed", "completed", "declined", "cancelled",
]
LegalBasis = Literal[
    "consent", "contract", "legal_obligation", "legitimate_interests",
    "public_task", "vital_interests", "other",
]


class PrivacyRequestCreate(BaseModel):
    organization_id: UUID
    candidate_id: UUID | None = None
    request_type: RequestType
    requester_email: str | None = Field(default=None, max_length=320)
    requested_scope: dict = Field(default_factory=dict)


class PrivacyRequestUpdate(BaseModel):
    status: RequestStatus
    affected_systems: list[str] = Field(default_factory=list)
    exception_details: str | None = Field(default=None, max_length=4000)
    retention_justification: str | None = Field(default=None, max_length=4000)


class NoticeCreate(BaseModel):
    organization_id: UUID
    version: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=120)
    notice_text: str = Field(min_length=1, max_length=50000)
    effective_at: datetime


class ProcessingRecordCreate(BaseModel):
    organization_id: UUID
    candidate_id: UUID
    purpose: str = Field(min_length=1, max_length=120)
    legal_basis: LegalBasis
    notice_id: UUID | None = None
    consent_status: Literal["granted", "withdrawn", "not_applicable"] | None = None
    consent_captured_at: datetime | None = None
    consent_withdrawn_at: datetime | None = None
    processing_preferences: dict = Field(default_factory=dict)


def _database_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("/notices")
async def list_notices(
    organization_id: UUID,
    purpose: str | None = Query(default=None, max_length=120),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, version, purpose, notice_text,
                              effective_at, retired_at, created_at
                       from public.privacy_notices
                       where organization_id = %s and (%s is null or purpose = %s)
                       order by purpose, effective_at desc""",
                    [organization_id, purpose, purpose],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/notices", status_code=201)
async def create_notice(
    payload: NoticeCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.privacy_notices
                       (organization_id, version, purpose, notice_text, effective_at, created_by)
                       values (%s, %s, %s, %s, %s, %s)
                       returning id, organization_id, version, purpose, effective_at, created_at""",
                    [payload.organization_id, payload.version, payload.purpose, payload.notice_text,
                     payload.effective_at, user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.notice_created', 'privacy_notice', %s, %s::jsonb)""",
                    [payload.organization_id, user_id, row["id"],
                     json.dumps({"version": payload.version, "purpose": payload.purpose})],
                )
                return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/processing-records", status_code=201)
async def create_processing_record(
    payload: ProcessingRecordCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if payload.legal_basis == "consent":
        if payload.consent_status not in {"granted", "withdrawn"} or payload.consent_captured_at is None:
            raise HTTPException(status_code=422, detail="Consent basis requires explicit consent status and capture timestamp")
        if payload.consent_status == "withdrawn" and payload.consent_withdrawn_at is None:
            raise HTTPException(status_code=422, detail="Withdrawn consent requires a withdrawal timestamp")
    elif payload.consent_status not in {None, "not_applicable"}:
        raise HTTPException(status_code=422, detail="Consent status must be separate from non-consent legal bases")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.candidates where id = %s and organization_id = %s",
                    [payload.candidate_id, payload.organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Candidate not found")
                if payload.notice_id is not None:
                    cursor.execute(
                        "select id from public.privacy_notices where id = %s and organization_id = %s",
                        [payload.notice_id, payload.organization_id],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Privacy notice does not belong to this organisation")
                cursor.execute(
                    """insert into public.candidate_processing_records
                       (organization_id, candidate_id, purpose, legal_basis, notice_id,
                        consent_status, consent_captured_at, consent_withdrawn_at,
                        processing_preferences, recorded_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                       returning id, organization_id, candidate_id, purpose, legal_basis,
                                 notice_id, consent_status, consent_captured_at,
                                 consent_withdrawn_at, processing_preferences, created_at""",
                    [payload.organization_id, payload.candidate_id, payload.purpose, payload.legal_basis,
                     payload.notice_id, payload.consent_status, payload.consent_captured_at,
                     payload.consent_withdrawn_at, json.dumps(payload.processing_preferences), user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.processing_record_created',
                               'candidate_processing_record', %s, %s::jsonb)""",
                    [payload.organization_id, user_id, row["id"],
                     json.dumps({"candidate_id": str(payload.candidate_id),
                                 "purpose": payload.purpose, "legal_basis": payload.legal_basis})],
                )
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/requests", status_code=201)
async def create_rights_request(
    payload: PrivacyRequestCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if payload.candidate_id is not None:
                    cursor.execute(
                        "select id from public.candidates where id = %s and organization_id = %s",
                        [payload.candidate_id, payload.organization_id],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Candidate not found")
                cursor.execute(
                    """insert into public.privacy_rights_requests
                       (organization_id, candidate_id, request_type, requester_email,
                        requested_scope, created_by)
                       values (%s, %s, %s, %s, %s::jsonb, %s)
                       returning id, organization_id, candidate_id, request_type, status,
                                 requested_scope, received_at, due_at, created_at""",
                    [payload.organization_id, payload.candidate_id, payload.request_type,
                     payload.requester_email, json.dumps(payload.requested_scope), user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.rights_request_created',
                               'privacy_rights_request', %s, %s::jsonb)""",
                    [payload.organization_id, user_id, row["id"],
                     json.dumps({"request_type": payload.request_type, "status": "received"})],
                )
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.get("/requests")
async def list_rights_requests(
    organization_id: UUID,
    status: RequestStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, candidate_id, request_type, status,
                              requester_email, requested_scope, affected_systems,
                              exception_details, retention_justification, received_at,
                              due_at, completed_at, created_at, updated_at
                       from public.privacy_rights_requests
                       where organization_id = %s and (%s is null or status = %s)
                       order by received_at desc limit %s""",
                    [organization_id, status, status, limit],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.patch("/requests/{request_id}")
async def update_rights_request(
    request_id: UUID,
    payload: PrivacyRequestUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id, status from public.privacy_rights_requests where id = %s",
                    [request_id],
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Privacy request not found")
                assert_org_admin(user_id, existing["organization_id"])
                completed_at = datetime.now().astimezone() if payload.status in {
                    "partially_completed", "completed", "declined", "cancelled"
                } else None
                if payload.status in {"partially_completed", "declined"} and not (
                    payload.exception_details or payload.retention_justification
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Document an exception or retention justification for partial completion or decline",
                    )
                cursor.execute(
                    """update public.privacy_rights_requests
                       set status = %s, affected_systems = %s::jsonb,
                           exception_details = %s, retention_justification = %s,
                           completed_at = %s, updated_by = %s, updated_at = now()
                       where id = %s
                       returning id, organization_id, candidate_id, request_type, status,
                                 affected_systems, exception_details, retention_justification,
                                 received_at, due_at, completed_at, updated_at""",
                    [payload.status, json.dumps(payload.affected_systems), payload.exception_details,
                     payload.retention_justification, completed_at, user_id, request_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.rights_request_status_changed',
                               'privacy_rights_request', %s, %s::jsonb)""",
                    [existing["organization_id"], user_id, request_id,
                     json.dumps({"from": existing["status"], "to": payload.status,
                                 "affected_systems": payload.affected_systems,
                                 "has_exception": bool(payload.exception_details),
                                 "has_retention_justification": bool(payload.retention_justification)})],
                )
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
