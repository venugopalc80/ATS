from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/notification-preferences", tags=["notifications"])

# Security, account recovery and critical service notices are not user-disableable.
ESSENTIAL_TYPES = {
    "account_security",
    "password_reset",
    "login_verification",
    "critical_service",
}


def is_essential_notification_type(notification_type: str) -> bool:
    """Keep whole essential notification namespaces non-disableable as well as exact keys."""
    return any(
        notification_type == prefix or notification_type.startswith(f"{prefix}.")
        for prefix in (*ESSENTIAL_TYPES, "security")
    )


class PreferenceUpdate(BaseModel):
    organization_id: UUID
    notification_type: str = Field(min_length=1, max_length=100, pattern="^[a-zA-Z0-9_.-]+$")
    channel: str = Field(pattern="^(in_app|email|sms)$")
    enabled: bool


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("")
async def list_preferences(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select notification_type, channel, enabled, updated_at
                    from public.notification_preferences
                    where organization_id=%s and user_id=%s
                    order by notification_type, channel
                    """,
                    [organization_id, user_id],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.put("")
async def update_preference(
    payload: PreferenceUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if not payload.enabled and is_essential_notification_type(payload.notification_type):
        raise HTTPException(status_code=422, detail="Essential security and service notices cannot be disabled")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.notification_preferences
                      (organization_id, user_id, notification_type, channel, enabled, updated_at)
                    values (%s,%s,%s,%s,%s,now())
                    on conflict (organization_id, user_id, notification_type, channel)
                    do update set enabled=excluded.enabled, updated_at=now()
                    returning notification_type, channel, enabled, updated_at
                    """,
                    [payload.organization_id, user_id, payload.notification_type, payload.channel, payload.enabled],
                )
                return cursor.fetchone()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
