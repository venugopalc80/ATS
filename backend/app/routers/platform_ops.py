from datetime import datetime
from typing import Literal
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

support_router = APIRouter(prefix="/api/support", tags=["support"])
platform_router = APIRouter(prefix="/api/platform", tags=["platform operations"])

SupportCategory = Literal["billing", "technical", "account", "security", "privacy", "other"]
SupportScope = Literal["case_metadata", "case_messages", "subscription_metadata", "service_health"]


class SupportCaseCreate(BaseModel):
    organization_id: UUID
    category: SupportCategory
    subject: str = Field(min_length=4, max_length=180)
    description: str = Field(min_length=10, max_length=8000)


class SupportAccessRequest(BaseModel):
    organization_id: UUID
    support_case_id: UUID
    purpose: str = Field(min_length=10, max_length=1000)
    scope: list[SupportScope] = Field(min_length=1, max_length=4)
    duration_minutes: int = Field(default=30, ge=5, le=60)


def assert_platform_operator(user_id: UUID) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select active from public.platform_operators where user_id=%s",
                    [user_id],
                )
                row = cursor.fetchone()
        if row is None or not row["active"]:
            raise HTTPException(status_code=403, detail="Platform operator access required")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform operations are unavailable") from exc


@support_router.post("/cases", status_code=201)
async def create_support_case(
    payload: SupportCaseCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.support_cases
                       (organization_id, created_by, category, subject, description)
                       values (%s, %s, %s, %s, %s)
                       returning id, organization_id, category, priority, status,
                                 subject, description, created_at, updated_at""",
                    [payload.organization_id, user_id, payload.category, payload.subject.strip(), payload.description.strip()],
                )
                case = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.case.created', 'support_case', %s, %s::jsonb)""",
                    [
                        payload.organization_id,
                        user_id,
                        case["id"],
                        json.dumps({"category": payload.category, "priority": "normal"}),
                    ],
                )
        return case
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support service is unavailable") from exc


@support_router.get("/cases")
async def list_support_cases(
    organization_id: UUID = Query(...),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, category, priority, status, subject, created_at,
                              updated_at, resolved_at
                       from public.support_cases
                       where organization_id=%s
                       order by updated_at desc limit 100""",
                    [organization_id],
                )
                cases = list(cursor.fetchall())
        return {"cases": cases}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support service is unavailable") from exc


@platform_router.post("/support/access-grants", status_code=201)
async def request_support_access(
    payload: SupportAccessRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select id from public.organizations where id=%s", [payload.organization_id])
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Organisation not found")
                cursor.execute(
                    "select id from public.support_cases where id=%s and organization_id=%s",
                    [payload.support_case_id, payload.organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Support case not found for this organisation")
                cursor.execute(
                    """insert into public.support_access_grants
                       (organization_id, support_case_id, operator_user_id, purpose, scope, expires_at)
                       values (%s, %s, %s, %s, %s, now() + (%s * interval '1 minute'))
                       returning id, organization_id, support_case_id, purpose, scope, requested_at, expires_at""",
                    [payload.organization_id, payload.support_case_id, user_id, payload.purpose.strip(),
                     list(dict.fromkeys(payload.scope)), payload.duration_minutes],
                )
                grant = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.access.requested', 'support_access_grant', %s, %s::jsonb)""",
                    [
                        payload.organization_id,
                        user_id,
                        grant["id"],
                        json.dumps({"purpose": payload.purpose.strip(), "scope": grant["scope"], "duration_minutes": payload.duration_minutes}),
                    ],
                )
        return grant
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support access request is unavailable") from exc


@support_router.get("/access-grants")
async def list_support_access_grants(
    organization_id: UUID = Query(...),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, support_case_id, operator_user_id, purpose, scope, requested_at,
                              approved_by_org_user_id, approved_at, expires_at, revoked_at
                       from public.support_access_grants
                       where organization_id=%s
                       order by requested_at desc limit 100""",
                    [organization_id],
                )
                grants = list(cursor.fetchall())
        return {"grants": grants}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support access grants are unavailable") from exc


@support_router.post("/access-grants/{grant_id}/approve")
async def approve_support_access(
    grant_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id, approved_at, expires_at, revoked_at from public.support_access_grants where id=%s",
                    [grant_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=404, detail="Support access request not found")
                organization_id = grant["organization_id"]
                assert_org_admin(user_id, organization_id)
                if grant["revoked_at"] is not None or grant["approved_at"] is not None:
                    raise HTTPException(status_code=409, detail="Support access request is already decided")
                cursor.execute(
                    """update public.support_access_grants
                       set approved_by_org_user_id=%s, approved_at=now()
                       where id=%s and approved_at is null and revoked_at is null and expires_at > now()
                       returning id, organization_id, approved_by_org_user_id, approved_at, expires_at""",
                    [user_id, grant_id],
                )
                approved = cursor.fetchone()
                if approved is None:
                    raise HTTPException(status_code=409, detail="Support access request has expired")
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.access.approved', 'support_access_grant', %s, '{}'::jsonb)""",
                    [organization_id, user_id, grant_id],
                )
        return approved
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support access approval is unavailable") from exc


@support_router.post("/access-grants/{grant_id}/revoke")
async def revoke_support_access(
    grant_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id, revoked_at from public.support_access_grants where id=%s",
                    [grant_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=404, detail="Support access grant not found")
                organization_id = grant["organization_id"]
                assert_org_admin(user_id, organization_id)
                if grant["revoked_at"] is not None:
                    return {"revoked": True}
                cursor.execute(
                    "update public.support_access_grants set revoked_at=now() where id=%s returning id, revoked_at",
                    [grant_id],
                )
                revoked = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.access.revoked', 'support_access_grant', %s, '{}'::jsonb)""",
                    [organization_id, user_id, grant_id],
                )
        return {"revoked": True, **revoked}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support access revocation is unavailable") from exc


@platform_router.get("/support/cases")
async def platform_list_support_cases(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, category, priority, status, subject,
                              assigned_operator_id, created_at, updated_at
                       from public.support_cases
                       where (%s::text is null or status=%s)
                       order by case priority when 'urgent' then 0 when 'high' then 1
                                 when 'normal' then 2 else 3 end, created_at
                       limit %s""",
                    [status, status, limit],
                )
                cases = list(cursor.fetchall())
        return {"cases": cases}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform support queue is unavailable") from exc


@platform_router.get("/support/cases/{case_id}")
async def platform_get_support_case(
    case_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Read only the tenant key before checking the customer's approval.
                cursor.execute("select organization_id from public.support_cases where id=%s", [case_id])
                case_ref = cursor.fetchone()
                if case_ref is None:
                    raise HTTPException(status_code=404, detail="Support case not found")
                cursor.execute(
                    """select id, purpose, scope, approved_by_org_user_id, expires_at
                       from public.support_access_grants
                       where organization_id=%s and support_case_id=%s and operator_user_id=%s
                         and approved_at is not null and revoked_at is null
                         and expires_at > now() and scope @> array['case_metadata']::text[]
                       order by approved_at desc limit 1""",
                    [case_ref["organization_id"], case_id, user_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=403, detail="Active organisation-approved support access is required")
                cursor.execute(
                    """select id, organization_id, category, priority, status, subject,
                              description, created_at, updated_at, resolved_at
                       from public.support_cases where id=%s""",
                    [case_id],
                )
                case = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.case.viewed', 'support_case', %s, %s::jsonb)""",
                    [
                        case["organization_id"], user_id, case_id,
                        json.dumps({"grant_id": str(grant["id"]), "purpose": grant["purpose"], "scope": grant["scope"]}),
                    ],
                )
        return case
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform support case is unavailable") from exc


@platform_router.get("/health")
async def platform_health(user_id: UUID = Depends(get_current_user_id)):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select now() as checked_at")
                checked_at = cursor.fetchone()["checked_at"]
                cursor.execute(
                    """select status, count(*) as count
                       from public.support_cases group by status order by status"""
                )
                support_counts = list(cursor.fetchall())
        return {
            "status": "ok",
            "database": "ok",
            "checked_at": checked_at,
            "support_cases_by_status": support_counts,
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform health check failed") from exc


class SupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class PlatformSupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    visibility: Literal["customer", "internal"] = "customer"


@support_router.get("/cases/{case_id}/messages")
async def list_customer_support_messages(
    case_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.support_cases where id=%s", [case_id])
                case_ref = cursor.fetchone()
                if case_ref is None:
                    raise HTTPException(status_code=404, detail="Support case not found")
                assert_org_member(user_id, case_ref["organization_id"])
                cursor.execute(
                    """select id, author_user_id, body, created_at
                       from public.support_case_messages
                       where support_case_id=%s and visibility='customer'
                       order by created_at""",
                    [case_id],
                )
                messages = list(cursor.fetchall())
        return {"messages": messages}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support messages are unavailable") from exc


@support_router.post("/cases/{case_id}/messages", status_code=201)
async def create_customer_support_message(
    case_id: UUID,
    payload: SupportMessageCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.support_cases where id=%s", [case_id])
                case_ref = cursor.fetchone()
                if case_ref is None:
                    raise HTTPException(status_code=404, detail="Support case not found")
                assert_org_member(user_id, case_ref["organization_id"])
                cursor.execute(
                    """insert into public.support_case_messages
                       (support_case_id, author_user_id, visibility, body)
                       values (%s, %s, 'customer', %s)
                       returning id, support_case_id, author_user_id, visibility, body, created_at""",
                    [case_id, user_id, payload.body.strip()],
                )
                message = cursor.fetchone()
                cursor.execute("update public.support_cases set updated_at=now() where id=%s", [case_id])
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.case.message_added', 'support_case', %s, '{}'::jsonb)""",
                    [case_ref["organization_id"], user_id, case_id],
                )
        return message
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Support message could not be saved") from exc


@platform_router.get("/support/cases/{case_id}/messages")
async def platform_list_support_messages(
    case_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.support_cases where id=%s", [case_id])
                case_ref = cursor.fetchone()
                if case_ref is None:
                    raise HTTPException(status_code=404, detail="Support case not found")
                cursor.execute(
                    """select id, purpose, scope
                       from public.support_access_grants
                       where organization_id=%s and support_case_id=%s and operator_user_id=%s
                         and approved_at is not null and revoked_at is null
                         and expires_at > now() and scope @> array['case_messages']::text[]
                       order by approved_at desc limit 1""",
                    [case_ref["organization_id"], case_id, user_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=403, detail="Active organisation-approved message access is required")
                cursor.execute(
                    """select id, author_user_id, author_operator_id, visibility, body, created_at
                       from public.support_case_messages
                       where support_case_id=%s order by created_at""",
                    [case_id],
                )
                messages = list(cursor.fetchall())
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.case.messages_viewed', 'support_case', %s, %s::jsonb)""",
                    [case_ref["organization_id"], user_id, case_id,
                     json.dumps({"grant_id": str(grant["id"]), "purpose": grant["purpose"]})],
                )
        return {"messages": messages}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform support messages are unavailable") from exc


@platform_router.post("/support/cases/{case_id}/messages", status_code=201)
async def platform_create_support_message(
    case_id: UUID,
    payload: PlatformSupportMessageCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_platform_operator(user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.support_cases where id=%s", [case_id])
                case_ref = cursor.fetchone()
                if case_ref is None:
                    raise HTTPException(status_code=404, detail="Support case not found")
                cursor.execute(
                    """select id, purpose
                       from public.support_access_grants
                       where organization_id=%s and support_case_id=%s and operator_user_id=%s
                         and approved_at is not null and revoked_at is null
                         and expires_at > now() and scope @> array['case_messages']::text[]
                       order by approved_at desc limit 1""",
                    [case_ref["organization_id"], case_id, user_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=403, detail="Active organisation-approved message access is required")
                cursor.execute(
                    """insert into public.support_case_messages
                       (support_case_id, author_operator_id, visibility, body)
                       values (%s, %s, %s, %s)
                       returning id, support_case_id, author_operator_id, visibility, body, created_at""",
                    [case_id, user_id, payload.visibility, payload.body.strip()],
                )
                message = cursor.fetchone()
                cursor.execute("update public.support_cases set updated_at=now() where id=%s", [case_id])
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'support.case.operator_message_added', 'support_case', %s, %s::jsonb)""",
                    [case_ref["organization_id"], user_id, case_id,
                     json.dumps({"grant_id": str(grant["id"]), "visibility": payload.visibility})],
                )
        return message
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Platform support message could not be saved") from exc
