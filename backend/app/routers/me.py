from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated

from app.auth import get_current_user_id
from app.db import get_connection

router = APIRouter(prefix="/api/me", tags=["me"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


@router.get("")
async def get_context(user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select o.id, o.name, o.country_code, m.role
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
    user_id: UUID = __import__("fastapi").Depends(get_current_user_id),
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
                insert into public.organizations (name, country_code)
                values (%s, %s)
                returning id, name, country_code
                """,
                [payload.name, payload.country_code],
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
