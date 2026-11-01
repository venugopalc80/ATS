import os
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

from app.db import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    get_connection,
)

bearer = HTTPBearer(auto_error=False)
ADMIN_ROLES = frozenset({"owner", "admin"})


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
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Permission service is temporarily unavailable") from exc


def assert_org_member(user_id: UUID, organization_id: UUID) -> None:
    get_org_role(user_id, organization_id)


def assert_org_admin(user_id: UUID, organization_id: UUID) -> None:
    role = get_org_role(user_id, organization_id)
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")


def require_permission(user_id: UUID, organization_id: UUID, permission_key: str) -> None:
    """Require membership and an active explicit grant; owner/admin have full access.

    This check is server-side. Call it before reading sensitive data, mutating
    records, or issuing signed document URLs. Resource queries must still scope
    the resource to organization_id to prevent cross-tenant access.
    """
    if not isinstance(permission_key, str) or not permission_key.strip():
        raise HTTPException(status_code=403, detail="Permission denied")

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
                membership = cursor.fetchone()
                if membership is None:
                    raise HTTPException(
                        status_code=403,
                        detail="You are not a member of this organization",
                    )

                if str(membership["role"]) in ADMIN_ROLES:
                    return

                cursor.execute(
                    """
                    select exists (
                        select 1
                        from public.member_permission_grants g
                        join public.organization_permissions p
                          on p.permission_key = g.permission_key
                        where g.organization_id = %s
                          and g.user_id = %s
                          and g.permission_key = %s
                          and g.revoked_at is null
                    ) as allowed
                    """,
                    [organization_id, user_id, permission_key],
                )
                result = cursor.fetchone()
                if result is None or not result["allowed"]:
                    raise HTTPException(
                        status_code=403,
                        detail="You do not have permission to perform this action",
                    )
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Permission service is temporarily unavailable",
        ) from exc
