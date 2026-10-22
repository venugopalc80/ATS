from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.communications import (
    InternalNoteCreate,
    MessageDraftCreate,
    TemplateCreate,
    ThreadCreate,
)

router = APIRouter(prefix="/api/communications", tags=["communications"])


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("/threads")
async def list_threads(
    organization_id: UUID,
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.applications where id=%s and organization_id=%s",
                    [application_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Application not found")
                cursor.execute(
                    """
                    select id, organization_id, application_id, candidate_id, subject,
                           created_by, created_at, updated_at
                    from public.communication_threads
                    where organization_id=%s and application_id=%s
                    order by created_at desc
                    """,
                    [organization_id, application_id],
                )
                return list(cursor.fetchall())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/threads", status_code=201)
async def create_thread(payload: ThreadCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select a.candidate_id
                    from public.applications a
                    join public.candidates c
                      on c.id=a.candidate_id and c.organization_id=a.organization_id
                    where a.id=%s and a.organization_id=%s
                    """,
                    [payload.application_id, payload.organization_id],
                )
                application = cursor.fetchone()
                if application is None:
                    raise HTTPException(status_code=404, detail="Application not found")
                cursor.execute(
                    """
                    insert into public.communication_threads
                      (organization_id, application_id, candidate_id, subject, created_by)
                    values (%s,%s,%s,%s,%s)
                    returning id, organization_id, application_id, candidate_id, subject,
                              created_by, created_at, updated_at
                    """,
                    [payload.organization_id, payload.application_id, application["candidate_id"], payload.subject, user_id],
                )
                return cursor.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/threads/{thread_id}/timeline")
async def get_timeline(
    thread_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.communication_threads where id=%s and organization_id=%s",
                    [thread_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Communication thread not found")
                cursor.execute(
                    """
                    select m.id, m.thread_id, m.visibility, m.channel, m.body_text,
                           m.subject, m.status, m.sender_user_id, m.template_id,
                           m.template_version, m.created_at, m.updated_at
                    from public.messages m
                    where m.organization_id=%s and m.thread_id=%s
                    order by m.created_at asc
                    """,
                    [organization_id, thread_id],
                )
                messages = list(cursor.fetchall())
                for message in messages:
                    cursor.execute(
                        """
                        select id, recipient_type, recipient_address, delivery_status, created_at
                        from public.message_recipients
                        where organization_id=%s and message_id=%s
                        order by created_at asc
                        """,
                        [organization_id, message["id"]],
                    )
                    message["recipients"] = list(cursor.fetchall())
                    cursor.execute(
                        """
                        select id, provider, event_type, occurred_at
                        from public.delivery_events
                        where organization_id=%s and message_id=%s
                        order by occurred_at asc
                        """,
                        [organization_id, message["id"]],
                    )
                    message["delivery_events"] = list(cursor.fetchall())
                return messages
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/threads/{thread_id}/notes", status_code=201)
async def add_internal_note(
    thread_id: UUID,
    payload: InternalNoteCreate,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.communication_threads where id=%s and organization_id=%s",
                    [thread_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Communication thread not found")
                cursor.execute(
                    """
                    insert into public.messages
                      (organization_id, thread_id, sender_user_id, visibility, channel, body_text, status)
                    values (%s,%s,%s,'internal','internal',%s,'internal')
                    returning id, thread_id, visibility, channel, body_text, status, sender_user_id, created_at
                    """,
                    [organization_id, thread_id, user_id, payload.body_text.strip()],
                )
                return cursor.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/threads/{thread_id}/messages", status_code=201)
async def create_message_draft(
    thread_id: UUID,
    payload: MessageDraftCreate,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.communication_threads where id=%s and organization_id=%s",
                    [thread_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Communication thread not found")
                template_version = payload.template_version
                if payload.template_id is not None:
                    if template_version is None:
                        raise HTTPException(status_code=422, detail="Template version is required")
                    cursor.execute(
                        """
                        select id from public.message_templates
                        where id=%s and organization_id=%s and version=%s and status='approved'
                        """,
                        [payload.template_id, organization_id, template_version],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Only an approved template version can be used")
                elif template_version is not None:
                    raise HTTPException(status_code=422, detail="Template ID is required with a template version")
                cursor.execute(
                    """
                    insert into public.messages
                      (organization_id, thread_id, sender_user_id, visibility, channel, body_text,
                       subject, template_id, template_version, status, idempotency_key)
                    values (%s,%s,%s,'candidate',%s,%s,%s,%s,%s,'draft',%s)
                    on conflict (organization_id, idempotency_key) where idempotency_key is not null
                    do nothing
                    returning id, thread_id, visibility, channel, body_text, subject, status,
                              template_id, template_version, sender_user_id, created_at
                    """,
                    [organization_id, thread_id, user_id, payload.channel, payload.body_text.strip(),
                     payload.subject, payload.template_id, template_version, payload.idempotency_key],
                )
                message = cursor.fetchone()
                if message is None:
                    cursor.execute(
                        """
                        select id, thread_id, visibility, channel, body_text, subject, status,
                               template_id, template_version, sender_user_id, created_at
                        from public.messages
                        where organization_id=%s and idempotency_key=%s
                        """,
                        [organization_id, payload.idempotency_key],
                    )
                    message = cursor.fetchone()
                    if message is None:
                        raise HTTPException(status_code=409, detail="Idempotency key conflict")
                    cursor.execute(
                        """
                        select recipient_address from public.message_recipients
                        where organization_id=%s and message_id=%s and recipient_type='to'
                        order by created_at asc limit 1
                        """,
                        [organization_id, message["id"]],
                    )
                    existing_recipient = cursor.fetchone()
                    same_request = (
                        message["body_text"] == payload.body_text.strip()
                        and message["subject"] == payload.subject
                        and message["channel"] == payload.channel
                        and existing_recipient is not None
                        and existing_recipient["recipient_address"] == payload.recipient_address.strip()
                    )
                    if not same_request:
                        raise HTTPException(status_code=409, detail="Idempotency key was already used for a different message")
                    return message
                cursor.execute(
                    """
                    insert into public.message_recipients
                      (organization_id, message_id, recipient_type, recipient_address, delivery_status)
                    values (%s,%s,'to',%s,'pending')
                    """,
                    [organization_id, message["id"], payload.recipient_address.strip()],
                )
                return message
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/templates")
async def list_templates(
    organization_id: UUID,
    status: str | None = Query(default=None, pattern="^(draft|approved|retired)$"),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id, template_key, version, name, channel, subject, body_text,
                           status, created_by, approved_by, approved_at, created_at
                    from public.message_templates
                    where organization_id=%s and (%s is null or status=%s)
                    order by template_key, version desc
                    """,
                    [organization_id, status, status],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/templates", status_code=201)
async def create_template(payload: TemplateCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Serialize version allocation per organisation/template key. Without this
                # transaction-scoped lock, concurrent creates can calculate the same version
                # and one request fails on the unique (organization_id, template_key, version)
                # constraint.
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    [f"{payload.organization_id}:{payload.template_key}"],
                )
                cursor.execute(
                    """
                    select coalesce(max(version),0)+1 as next_version
                    from public.message_templates
                    where organization_id=%s and template_key=%s
                    """,
                    [payload.organization_id, payload.template_key],
                )
                version = cursor.fetchone()["next_version"]
                cursor.execute(
                    """
                    insert into public.message_templates
                      (organization_id, template_key, version, name, channel, subject, body_text, created_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)
                    returning id, template_key, version, name, channel, subject, body_text,
                              status, created_by, created_at
                    """,
                    [payload.organization_id, payload.template_key, version, payload.name,
                     payload.channel, payload.subject, payload.body_text.strip(), user_id],
                )
                return cursor.fetchone()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/templates/{template_id}/approve")
async def approve_template(
    template_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update public.message_templates
                    set status='approved', approved_by=%s, approved_at=now()
                    where id=%s and organization_id=%s and status='draft'
                    returning id, template_key, version, name, channel, subject, body_text,
                              status, approved_by, approved_at
                    """,
                    [user_id, template_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Draft template not found")
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
