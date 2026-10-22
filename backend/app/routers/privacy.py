import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

RequestType = Literal["access", "correction", "restriction", "erasure", "portability", "objection", "other"]
RequestStatus = Literal[
    "received", "identity_verification", "in_progress", "awaiting_information",
    "partially_completed", "completed", "declined", "cancelled",
]
IdentityVerificationMethod = Literal["existing_account", "email_challenge", "document_review", "other"]
LegalBasis = Literal[
    "consent", "contract", "legal_obligation", "legitimate_interests",
    "public_task", "vital_interests", "other",
]

# Only these categories have an explicit, reviewed retention clock. Unknown categories
# are reported as unsupported rather than being mapped to an arbitrary table.
RETENTION_CATEGORY_CONFIG = {
    "candidate_profile": {
        "table": "candidates",
        "target_table": "candidates",
        "due_expression": "coalesce(r.retention_until, r.created_at + (%s * interval '1 day'))",
        "active_filter": "true",
        "clock_start": "created_at; an explicit retention_until overrides the calculated date",
    },
    "candidate_document": {
        "table": "candidate_documents",
        "target_table": "candidate_documents",
        "due_expression": "r.created_at + (%s * interval '1 day')",
        "active_filter": "r.deleted_at is null",
        "clock_start": "document created_at",
    },
    "processing_record": {
        "table": "candidate_processing_records",
        "target_table": "candidate_processing_records",
        "due_expression": "r.created_at + (%s * interval '1 day')",
        "active_filter": "true",
        "clock_start": "processing record created_at",
    },
}


def retention_category_definition(data_category: str) -> dict | None:
    """Return a fixed SQL mapping; caller input is never used as SQL syntax."""
    return RETENTION_CATEGORY_CONFIG.get(data_category)


PRIVACY_REQUEST_TRANSITIONS = {
    "received": {"identity_verification", "cancelled"},
    "identity_verification": {"in_progress", "awaiting_information", "declined", "cancelled"},
    "in_progress": {"awaiting_information", "partially_completed", "completed", "declined", "cancelled"},
    "awaiting_information": {"in_progress", "cancelled"},
    "partially_completed": {"in_progress", "completed", "declined", "cancelled"},
    "completed": set(),
    "declined": set(),
    "cancelled": set(),
}


def is_privacy_request_transition_allowed(current_status: str, next_status: str) -> bool:
    """Keep API validation aligned with the database transition guard."""
    return next_status == current_status or next_status in PRIVACY_REQUEST_TRANSITIONS.get(current_status, set())


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
    identity_verification_method: IdentityVerificationMethod | None = None

    @model_validator(mode="after")
    def validate_exceptions(self):
        if self.status in {"partially_completed", "declined"} and not (
            (self.exception_details or "").strip() or (self.retention_justification or "").strip()
        ):
            raise ValueError("Partial completion or decline requires a documented exception or retention justification")
        return self


class NoticeCreate(BaseModel):
    organization_id: UUID
    version: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=120)
    notice_text: str = Field(min_length=1, max_length=50000)
    effective_at: datetime


class RetentionPolicyCreate(BaseModel):
    organization_id: UUID
    data_category: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=120)
    jurisdiction: Literal["GB", "US", "IN", "AU", "GLOBAL"]
    retention_days: int = Field(ge=0, le=36500)
    action: Literal["review", "delete", "anonymise"]
    version: int = Field(ge=1)
    effective_at: datetime


class RetentionExceptionCreate(BaseModel):
    organization_id: UUID
    policy_id: UUID | None = None
    target_table: Literal["candidates", "applications", "candidate_documents", "candidate_processing_records", "audit_events"]
    target_record_id: UUID
    exception_type: Literal["legal_hold", "legal_requirement", "dispute", "manual_review", "other"]
    reason: str = Field(min_length=1, max_length=4000)
    starts_at: datetime
    ends_at: datetime | None = None


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

    @model_validator(mode="after")
    def validate_consent_fields(self):
        if self.legal_basis == "consent":
            if self.consent_status not in {"granted", "withdrawn"} or self.consent_captured_at is None:
                raise ValueError("Consent basis requires an explicit status and capture timestamp")
            if self.consent_status == "withdrawn" and self.consent_withdrawn_at is None:
                raise ValueError("Withdrawn consent requires a withdrawal timestamp")
        elif self.consent_status not in {None, "not_applicable"} or self.consent_captured_at is not None or self.consent_withdrawn_at is not None:
            raise ValueError("Consent evidence must not be used for a non-consent legal basis")
        if self.consent_withdrawn_at and self.consent_captured_at and self.consent_withdrawn_at < self.consent_captured_at:
            raise ValueError("Consent withdrawal cannot predate consent capture")
        return self


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
async def create_notice(payload: NoticeCreate, user_id: UUID = Depends(get_current_user_id)):
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


@router.get("/retention-policies")
async def list_retention_policies(
    organization_id: UUID,
    enabled: bool | None = None,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, data_category, purpose, jurisdiction,
                              retention_days, action, version, enabled, effective_at, created_at
                       from public.retention_policies
                       where organization_id = %s and (%s is null or enabled = %s)
                       order by data_category, purpose, jurisdiction, version desc""",
                    [organization_id, enabled, enabled],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.get("/retention-preview")
async def preview_retention(
    organization_id: UUID,
    policy_id: UUID | None = None,
    as_of: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    user_id: UUID = Depends(get_current_user_id),
):
    """Non-destructive retention preview; only the audit trail is written."""
    assert_org_admin(user_id, organization_id)
    preview_at = as_of or datetime.now(timezone.utc)
    if preview_at.tzinfo is None or preview_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="'as_of' must include a timezone")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, data_category, purpose, jurisdiction, retention_days,
                              action, version, effective_at
                       from public.retention_policies
                       where organization_id = %s and enabled = true
                         and effective_at <= %s and (%s is null or id = %s)
                       order by data_category, purpose, jurisdiction, version desc
                       limit 50""",
                    [organization_id, preview_at, policy_id, policy_id],
                )
                policies = list(cursor.fetchall())
                if policy_id is not None and not policies:
                    raise HTTPException(status_code=404, detail="Enabled retention policy not found for this organisation and preview time")

                previews = []
                for policy in policies:
                    config = retention_category_definition(policy["data_category"])
                    if config is None:
                        previews.append({
                            "policy_id": policy["id"],
                            "data_category": policy["data_category"],
                            "purpose": policy["purpose"],
                            "jurisdiction": policy["jurisdiction"],
                            "retention_days": policy["retention_days"],
                            "action": policy["action"],
                            "version": policy["version"],
                            "status": "unsupported_category",
                            "clock_start": None,
                            "eligible_count": 0,
                            "excluded_active_exception_count": 0,
                            "previously_processed_count": 0,
                            "items": [],
                            "message": "No explicit retention clock is configured for this category; no records were scanned.",
                        })
                        continue

                    table = config["table"]
                    target_table = config["target_table"]
                    due_expression = config["due_expression"]
                    active_filter = config["active_filter"]
                    common_exception = (
                        "e.organization_id = r.organization_id "
                        "and e.target_table = %s and e.target_record_id = r.id "
                        "and e.starts_at <= %s and (e.ends_at is null or e.ends_at > %s) "
                        "and (e.policy_id is null or e.policy_id = %s) "
                        "and (e.exception_type = 'legal_hold' or e.approved_by is not null)"
                    )
                    common_processed = (
                        "l.organization_id = r.organization_id and l.policy_id = %s "
                        "and l.target_table = %s and l.target_record_id = r.id "
                        "and l.action = %s and l.status = 'succeeded'"
                    )
                    cursor.execute(
                        f"""select
                              count(*) filter (where has_active_exception) as held_count,
                              count(*) filter (where previously_processed) as processed_count,
                              count(*) filter (where not has_active_exception and not previously_processed) as eligible_count
                            from (
                              select r.id,
                                exists (select 1 from public.retention_exceptions e where {common_exception}) as has_active_exception,
                                exists (select 1 from public.retention_execution_logs l where {common_processed}) as previously_processed
                              from public.{table} r
                              where r.organization_id = %s and {active_filter}
                                and {due_expression} <= %s
                            ) due_records""",
                        [target_table, preview_at, preview_at, policy["id"],
                         policy["id"], target_table, policy["action"],
                         organization_id, policy["retention_days"], preview_at],
                    )
                    counts = cursor.fetchone()

                    cursor.execute(
                        f"""select r.id, r.created_at, {due_expression} as due_at
                            from public.{table} r
                            where r.organization_id = %s and {active_filter}
                              and {due_expression} <= %s
                              and not exists (
                                select 1 from public.retention_exceptions e where {common_exception}
                              )
                              and not exists (
                                select 1 from public.retention_execution_logs l where {common_processed}
                              )
                            order by due_at asc, r.id asc
                            limit %s""",
                        [policy["retention_days"], organization_id, policy["retention_days"], preview_at,
                         target_table, preview_at, preview_at, policy["id"],
                         policy["id"], target_table, policy["action"], limit],
                    )
                    items = list(cursor.fetchall())
                    previews.append({
                        "policy_id": policy["id"],
                        "data_category": policy["data_category"],
                        "purpose": policy["purpose"],
                        "jurisdiction": policy["jurisdiction"],
                        "retention_days": policy["retention_days"],
                        "action": policy["action"],
                        "version": policy["version"],
                        "status": "preview_ready",
                        "clock_start": config["clock_start"],
                        "eligible_count": counts["eligible_count"],
                        "excluded_active_exception_count": counts["held_count"],
                        "previously_processed_count": counts["processed_count"],
                        "items": items,
                        "items_truncated": counts["eligible_count"] > len(items),
                    })

                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, metadata)
                       values (%s, %s, 'privacy.retention_previewed', 'retention_preview', %s::jsonb)""",
                    [organization_id, user_id, json.dumps({
                        "as_of": preview_at.isoformat(),
                        "policies_scanned": len(policies),
                        "eligible_count": sum(item.get("eligible_count", 0) for item in previews),
                        "unsupported_category_count": sum(item.get("status") == "unsupported_category" for item in previews),
                    })],
                )
                return {
                    "organization_id": organization_id,
                    "as_of": preview_at,
                    "preview_only": True,
                    "deletion_executed": False,
                    "anonymisation_executed": False,
                    "policies_scanned": len(policies),
                    "policy_list_truncated": len(policies) == 50 and policy_id is None,
                    "policies": previews,
                }
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/retention-policies", status_code=201)
async def create_retention_policy(payload: RetentionPolicyCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.retention_policies
                       (organization_id, data_category, purpose, jurisdiction,
                        retention_days, action, version, effective_at, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       returning id, organization_id, data_category, purpose, jurisdiction,
                                 retention_days, action, version, enabled, effective_at, created_at""",
                    [payload.organization_id, payload.data_category, payload.purpose,
                     payload.jurisdiction, payload.retention_days, payload.action,
                     payload.version, payload.effective_at, user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.retention_policy_created',
                               'retention_policy', %s, %s::jsonb)""",
                    [payload.organization_id, user_id, row["id"],
                     json.dumps({"data_category": payload.data_category, "purpose": payload.purpose,
                                 "jurisdiction": payload.jurisdiction, "version": payload.version,
                                 "action": payload.action, "retention_days": payload.retention_days})],
                )
                return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.get("/retention-exceptions")
async def list_retention_exceptions(
    organization_id: UUID,
    active_only: bool = True,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, policy_id, target_table, target_record_id,
                              exception_type, reason, starts_at, ends_at, approved_by, created_at
                       from public.retention_exceptions
                       where organization_id = %s
                         and (%s = false or (starts_at <= now() and (ends_at is null or ends_at > now())))
                       order by starts_at desc""",
                    [organization_id, active_only],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/retention-exceptions", status_code=201)
async def create_retention_exception(payload: RetentionExceptionCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    if payload.ends_at is not None and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="Exception end must be after its start")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if payload.policy_id is not None:
                    cursor.execute(
                        "select id from public.retention_policies where id = %s and organization_id = %s",
                        [payload.policy_id, payload.organization_id],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Retention policy does not belong to this organisation")
                cursor.execute(
                    """insert into public.retention_exceptions
                       (organization_id, policy_id, target_table, target_record_id,
                        exception_type, reason, starts_at, ends_at, approved_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       returning id, organization_id, policy_id, target_table, target_record_id,
                                 exception_type, reason, starts_at, ends_at, approved_by, created_at""",
                    [payload.organization_id, payload.policy_id, payload.target_table,
                     payload.target_record_id, payload.exception_type, payload.reason,
                     payload.starts_at, payload.ends_at, user_id],
                )
                row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'privacy.retention_exception_created',
                               'retention_exception', %s, %s::jsonb)""",
                    [payload.organization_id, user_id, row["id"],
                     json.dumps({"exception_type": payload.exception_type,
                                 "target_table": payload.target_table,
                                 "target_record_id": str(payload.target_record_id)})],
                )
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/processing-records", status_code=201)
async def create_processing_record(payload: ProcessingRecordCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
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
async def create_rights_request(payload: PrivacyRequestCreate, user_id: UUID = Depends(get_current_user_id)):
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
                    "select organization_id, status, identity_verified_at, identity_verified_by, identity_verification_method from public.privacy_rights_requests where id = %s",
                    [request_id],
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Privacy request not found")
                assert_org_admin(user_id, existing["organization_id"])
                if not is_privacy_request_transition_allowed(existing["status"], payload.status):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Invalid privacy request transition: {existing['status']} -> {payload.status}",
                    )
                if existing["status"] == "identity_verification" and payload.status == "in_progress":
                    if payload.identity_verification_method is None:
                        raise HTTPException(status_code=422, detail="Identity verification method is required before processing can begin")
                completed_at = datetime.now(timezone.utc) if payload.status in {
                    "partially_completed", "completed", "declined", "cancelled"
                } else None
                identity_verified_at = datetime.now(timezone.utc) if (
                    existing["status"] == "identity_verification" and payload.status == "in_progress"
                ) else existing["identity_verified_at"]
                identity_verified_by = user_id if identity_verified_at is not None else existing["identity_verified_by"]
                identity_verification_method = (
                    payload.identity_verification_method if identity_verified_at is not None
                    else existing["identity_verification_method"]
                )
                cursor.execute(
                    """update public.privacy_rights_requests
                       set status = %s, affected_systems = %s::jsonb,
                           exception_details = %s, retention_justification = %s,
                           completed_at = %s, identity_verified_at = %s, identity_verified_by = %s,
                           identity_verification_method = %s, updated_by = %s, updated_at = now()
                       where id = %s
                       returning id, organization_id, candidate_id, request_type, status,
                                 affected_systems, exception_details, retention_justification,
                                 received_at, due_at, completed_at, updated_at""",
                    [payload.status, json.dumps(payload.affected_systems), payload.exception_details,
                     payload.retention_justification, completed_at, identity_verified_at,
                     identity_verified_by, identity_verification_method, user_id, request_id],
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
                                 "has_exception": bool(payload.exception_details and payload.exception_details.strip()),
                                 "has_retention_justification": bool(payload.retention_justification and payload.retention_justification.strip()),
                                 "identity_verification_method": identity_verification_method})],
                )
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
