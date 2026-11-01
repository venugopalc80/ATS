from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.auth import assert_org_admin, get_current_user_id
from app.db import get_connection

router = APIRouter(prefix="/api/me", tags=["me"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class JobReferenceSettingsUpdate(BaseModel):
    prefix: Annotated[str, StringConstraints(min_length=2, max_length=8, pattern=r"^[A-Za-z][A-Za-z0-9]{1,7}$")]

    @field_validator("prefix")
    @classmethod
    def normalise_prefix(cls, value: str) -> str:
        return value.strip().upper()


def derive_job_reference_prefix(organization_name: str) -> str:
    """Create a short, readable default prefix without hard-coding a tenant."""
    import re

    compact = re.sub(r"[^A-Z0-9]", "", organization_name.upper())
    if not compact or not compact[0].isalpha():
        return "JOB"
    prefix = compact[:3]
    return prefix if len(prefix) >= 2 else "JOB"


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
    user_id: UUID = Depends(get_current_user_id),
):
    prefix = derive_job_reference_prefix(payload.name)
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
                insert into public.organizations (name, country_code, job_reference_prefix)
                values (%s, %s, %s)
                returning id, name, country_code, job_reference_prefix
                """,
                [payload.name, payload.country_code, prefix],
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


@router.get("/organizations/{organization_id}/job-reference-settings")
async def get_job_reference_settings(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select job_reference_prefix, job_reference_next_number
                from public.organizations
                where id = %s
                """,
                [organization_id],
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return {
        "prefix": row["job_reference_prefix"],
        "next_number": row["job_reference_next_number"],
        "preview": f'{row["job_reference_prefix"]}-{row["job_reference_next_number"]:03d}',
    }


@router.put("/organizations/{organization_id}/job-reference-settings")
async def update_job_reference_settings(
    organization_id: UUID,
    payload: JobReferenceSettingsUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    prefix = payload.prefix
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.organizations o
                   set job_reference_prefix = %s,
                       job_reference_next_number = greatest(
                         o.job_reference_next_number,
                         coalesce((
                           select max(substring(j.job_code from length(%s) + 2)::bigint) + 1
                             from public.jobs j
                            where j.organization_id = o.id
                              and j.job_code ~ ('^' || %s || '-[0-9]+$')
                         ), 1),
                         1
                       ),
                       updated_at = now()
                 where o.id = %s
                returning job_reference_prefix, job_reference_next_number
                """,
                [prefix, prefix, prefix, organization_id],
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return {
        "prefix": row["job_reference_prefix"],
        "next_number": row["job_reference_next_number"],
        "preview": f'{row["job_reference_prefix"]}-{row["job_reference_next_number"]:03d}',
    }
