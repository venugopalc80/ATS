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


def assert_org_member(user_id: UUID, organization_id: UUID) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select 1
                    from public.organization_members
                    where organization_id = %s and user_id = %s
                    """,
                    [organization_id, user_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=403, detail="You are not a member of this organization")
    except HTTPException:
        raise
