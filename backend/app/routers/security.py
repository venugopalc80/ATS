from fastapi import APIRouter, Depends

from app.auth import get_current_auth_claims, is_mfa_verified

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/session")
async def current_session_security(claims: dict = Depends(get_current_auth_claims)):
    """Expose only the current session's security posture, never the raw JWT."""
    methods = []
    for item in claims.get("amr", []):
        if not isinstance(item, dict):
            continue
        method = item.get("method")
        if not isinstance(method, str) or not method:
            continue
        entry = {"method": method}
        timestamp = item.get("timestamp")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            entry["timestamp"] = timestamp
        methods.append(entry)

    return {
        "authenticated": True,
        "assurance_level": claims.get("aal", "aal1"),
        "mfa_verified": is_mfa_verified(claims),
        "issued_at": claims.get("iat"),
        "expires_at": claims.get("exp"),
        "authentication_methods": methods,
        "session_management": "supabase_auth",
    }
