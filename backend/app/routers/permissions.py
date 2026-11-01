import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/organizations", tags=["permissions"])


class PermissionGrantCreate(BaseModel):
    permission_key: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


class PermissionRevoke(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _database_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Permission service is temporarily unavailable")


@router.post("/{organization_id}/members/{member_user_id}/permissions", status_code=201)
async def grant_member_permission(
    organization_id: UUID,
    member_user_id: UUID,
    payload: PermissionGrantCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    """Grant a permission to a current organisation member; owner/admin only."""
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select 1 from public.organization_members
                    where organization_id = %s and user_id = %s
                    """,
                    [organization_id, member_user_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Organisation member not found")

                cursor.execute(
                    "select 1 from public.organization_permissions where permission_key = %s",
                    [payload.permission_key],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Unknown permission")

                cursor.execute(
                    """
                    insert into public.member_permission_grants
                        (organization_id, user_id, permission_key, granted_by)
                    values (%s, %s, %s, %s)
                    on conflict (organization_id, user_id, permission_key)
                        where revoked_at is null
                    do nothing
                    returning id, organization_id, user_id, permission_key, granted_by, granted_at
                    """,
                    [organization_id, member_user_id, payload.permission_key, user_id],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=409, detail="This permission is already active for the member")

                cursor.execute(
                    """
                    insert into public.audit_events
                        (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                    values (%s, %s, 'permission.granted', 'member_permission_grant', %s, %s::jsonb)
                    """,
                    [organization_id, user_id, grant["id"], json.dumps({
                        "member_user_id": str(member_user_id),
                        "permission_key": payload.permission_key,
                    })],
                )
                return grant
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{organization_id}/members/{member_user_id}/permissions/{permission_key}/revoke")
async def revoke_member_permission(
    organization_id: UUID,
    member_user_id: UUID,
    permission_key: str,
    payload: PermissionRevoke,
    user_id: UUID = Depends(get_current_user_id),
):
    """Revoke an active permission; retain the grant row as audit history."""
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update public.member_permission_grants
                    set revoked_at = now(), revoked_by = %s, revocation_reason = %s
                    where organization_id = %s
                      and user_id = %s
                      and permission_key = %s
                      and revoked_at is null
                    returning id, organization_id, user_id, permission_key, revoked_by, revoked_at
                    """,
                    [user_id, payload.reason, organization_id, member_user_id, permission_key],
                )
                grant = cursor.fetchone()
                if grant is None:
                    raise HTTPException(status_code=404, detail="Active permission grant not found")

                cursor.execute(
                    """
                    insert into public.audit_events
                        (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                    values (%s, %s, 'permission.revoked', 'member_permission_grant', %s, %s::jsonb)
                    """,
                    [organization_id, user_id, grant["id"], json.dumps({
                        "member_user_id": str(member_user_id),
                        "permission_key": permission_key,
                        "reason": payload.reason,
                    })],
                )
                return grant
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_unavailable(exc) from exc
