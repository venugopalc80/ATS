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


def is_mfa_verified(claims: dict) -> bool:
    """Return true only for a cryptographically verified Supabase AAL2 claim."""
    return claims.get("aal", "aal1") == "aal2"


def get_current_auth_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """Return verified JWT claims after the existing live user check succeeds."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        response = _auth_client().auth.get_claims(credentials.credentials)
        claims = getattr(response, "claims", None)
        if not isinstance(claims, dict):
            raise HTTPException(status_code=401, detail="Invalid authentication claims")
        if claims.get("sub") != str(user_id) or claims.get("role") != "authenticated":
            raise HTTPException(status_code=401, detail="Invalid authentication claims")
        return claims
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc


def require_mfa(claims: dict = Depends(get_current_auth_claims)) -> dict:
    """Dependency for sensitive routes that require a verified second factor."""
    if not is_mfa_verified(claims):
        raise HTTPException(
            status_code=403,
            detail={"code": "mfa_required", "message": "Complete multi-factor authentication to continue"},
        )
    return claims

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
