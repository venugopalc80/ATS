import os
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

from app.db import get_connection

bearer = HTTPBearer(auto_error=False)


def _auth_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return create_client(url, key)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        response = _auth_client().auth.get_user(credentials.credentials)
        user = response.user
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return UUID(str(user.id))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc


def get_org_role(user_id: UUID, organization_id: UUID) -> str:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select role
                    from public.organization_members
                    where organization_id = %s and user_id = %s
                    """,
                    [organization_id, user_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=403, detail="You are not a member of this organization")
                return str(row["role"])
    except HTTPException:
        raise


def assert_org_member(user_id: UUID, organization_id: UUID) -> None:
    get_org_role(user_id, organization_id)


def assert_org_admin(user_id: UUID, organization_id: UUID) -> None:
    role = get_org_role(user_id, organization_id)
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Admin access required")


def has_org_permission(user_id: UUID, organization_id: UUID, permission_key: str) -> bool:
    """Resolve the user's effective organisation permission.

    Owners retain full access. Administrators cannot receive ownership transfer
    rights. Active member overrides take precedence over the role template.
    """
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        m.role,
                        case
                            when m.role = 'owner' then true
                            when m.role = 'admin' and %s = 'ownership.transfer' then false
                            when override.effect is not null then override.effect = 'allow'
                            else coalesce(role_permission.allowed, false)
                        end as allowed
                    from public.organization_members m
                    left join public.organization_roles role_template
                      on role_template.organization_id = m.organization_id
                     and (
                          (m.custom_role_id is not null and role_template.id = m.custom_role_id)
                          or
                          (m.custom_role_id is null and role_template.role_key = m.role)
                     )
                    left join public.organization_role_permissions role_permission
                      on role_permission.organization_id = m.organization_id
                     and role_permission.role_id = role_template.id
                     and role_permission.permission_key = %s
                    left join public.organization_member_permission_overrides override
                      on override.organization_id = m.organization_id
                     and override.user_id = m.user_id
                     and override.permission_key = %s
                     and (override.expires_at is null or override.expires_at > now())
                    where m.organization_id = %s and m.user_id = %s
                    """,
                    [permission_key, permission_key, permission_key, organization_id, user_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=403, detail="You are not a member of this organisation")
                return bool(row["allowed"])
    except HTTPException:
        raise


def assert_org_permission(user_id: UUID, organization_id: UUID, permission_key: str) -> None:
    """Raise 403 unless the user has the requested effective permission."""
    if not has_org_permission(user_id, organization_id, permission_key):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission_key}")
