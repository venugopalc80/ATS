from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing import Annotated

from app.auth import assert_org_admin, get_current_user_id
from app.db import get_connection

router = APIRouter(prefix="/api/me", tags=["me"])


def validate_iana_timezone(value: str) -> str:
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use a valid IANA timezone, for example Europe/London or America/New_York")
    return value


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_iana_timezone(value)


class OrganizationSettingsUpdate(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_iana_timezone(value)


@router.get("")
async def get_context(user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select o.id, o.name, o.country_code, o.timezone, m.role
                from public.organization_members m
                join public.organizations o on o.id = m.organization_id
                where m.user_id = %s
                order by o.created_at
                """,
                [user_id],
            )
            organizations = list(cursor.fetchall())
    return {"user_id": str(user_id), "organizations": organizations}


@router.post("/organizations", status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.profiles (id, email)
                values (%s, null)
                on conflict (id) do nothing
                """,
                [user_id],
            )
            cursor.execute(
                """
                insert into public.organizations (name, country_code, timezone)
                values (%s, %s, %s)
                returning id, name, country_code, timezone
                """,
                [payload.name, payload.country_code, payload.timezone],
            )
            organization = cursor.fetchone()
            cursor.execute(
                """
                insert into public.organization_members (organization_id, user_id, role)
                values (%s, %s, 'owner')
                """,
                [organization["id"], user_id],
            )
    return {"organization": organization, "role": "owner"}


@router.patch("/organizations/{organization_id}/settings")
async def update_organization_settings(
    organization_id: UUID,
    payload: OrganizationSettingsUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    # Authorize against the requested organisation before issuing any update.
    assert_org_admin(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.organizations
                set timezone = %s
                where id = %s
                returning id, timezone
                """,
                [payload.timezone, organization_id],
            )
            organization = cursor.fetchone()
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {"organization": organization}
