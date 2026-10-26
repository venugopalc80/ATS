from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/audit", tags=["audit"])

def validate_security_event_window(since: datetime | None, until: datetime | None) -> None:
    """Reject ambiguous timestamps before comparing or querying PostgreSQL."""
    for field_name, value in (("since", since), ("until", until)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail=f"'{field_name}' must include a timezone")
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="'since' must be earlier than or equal to 'until'")


@router.get("/application/{application_id}")
async def application_audit(
    application_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.applications where id=%s", [application_id])
                application = cursor.fetchone()
                if application is None:
                    raise HTTPException(status_code=404, detail="Application not found")
                assert_org_member(user_id, application["organization_id"])
                cursor.execute(
                    """select id, actor_user_id, action, entity_type, entity_id, metadata, created_at
                       from public.audit_events
                       where organization_id=%s and entity_type='application' and entity_id=%s
                       order by created_at desc limit %s""",
                    [application["organization_id"], application_id, limit],
                )
                return list(cursor.fetchall())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


@router.get("/security-events")
async def security_events(
    organization_id: UUID,
    action: str | None = Query(default=None, max_length=120),
    outcome: str | None = Query(default=None, pattern="^(success|failure|blocked|unknown)$"),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    validate_security_event_window(since, until)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, actor_user_id, action, target_type,
                              target_id, outcome, source_service, request_id, ip_address,
                              user_agent, metadata, occurred_at
                       from public.security_events
                       where organization_id = %s
                         and (%s is null or action = %s)
                         and (%s is null or outcome = %s)
                         and (%s is null or occurred_at >= %s)
                         and (%s is null or occurred_at <= %s)
                       order by occurred_at desc limit %s""",
                    [organization_id, action, action, outcome, outcome,
                     since, since, until, until, limit],
                )
                rows = list(cursor.fetchall())
                cursor.execute(
                    """insert into public.security_events
                       (organization_id, actor_user_id, action, target_type, outcome,
                        source_service, metadata)
                       values (%s, %s, 'security_events.viewed', 'security_event_collection',
                               'success', 'api', %s::jsonb)""",
                    [organization_id, user_id, '{"result_count": ' + str(len(rows)) + '}'],
                )
                return rows
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc
