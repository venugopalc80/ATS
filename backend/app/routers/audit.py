from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/audit", tags=["audit"])

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
