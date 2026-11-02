import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing import Annotated

from app.auth import assert_org_permission, get_current_user_id, get_org_role, bearer, _auth_client
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


class OrganizationInviteCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: str = "recruiter"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        import re
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        allowed = {"admin", "recruiter", "hiring_manager", "viewer"}
        if value not in allowed:
            raise ValueError("Role must be admin, recruiter, hiring_manager or viewer")
        return value


class OrganizationInviteAccept(BaseModel):
    invitation_id: UUID
    token: str = Field(min_length=32, max_length=256)


def get_verified_user_email(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        response = _auth_client().auth.get_user(credentials.credentials)
        user = response.user
        if user is None or not user.email:
            raise HTTPException(status_code=401, detail="A valid email account is required")
        if not getattr(user, "email_confirmed_at", None):
            raise HTTPException(status_code=403, detail="Confirm your email address before accepting an invitation")
        return user.email.strip().lower()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc


def _supabase_admin_invite(email: str, redirect_to: str, organization_name: str) -> bool:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return False
    url = supabase_url + "/auth/v1/invite?" + urlencode({"redirect_to": redirect_to})
    try:
        response = requests.post(
            url,
            headers={"apikey": service_key, "Authorization": "Bearer " + service_key, "Content-Type": "application/json"},
            json={"email": email, "data": {"invited_to_organization": organization_name}},
            timeout=15,
        )
    except requests.RequestException:
        return False
    return response.status_code < 400

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
    assert_org_permission(user_id, organization_id, "organization.settings.manage")
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


@router.get("/organizations/{organization_id}/invitations")
async def list_organization_invitations(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.invite")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select id, email, role, expires_at, accepted_at, created_at
                from public.organization_invitations
                where organization_id = %s and accepted_at is null and expires_at > now()
                order by created_at desc
                """,
                [organization_id],
            )
            invitations = list(cursor.fetchall())
    return {"invitations": invitations}


@router.post("/organizations/{organization_id}/invitations", status_code=201)
async def create_organization_invitation(
    organization_id: UUID,
    payload: OrganizationInviteCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.invite")
    if payload.role == "admin" and get_org_role(user_id, organization_id) != "owner":
        raise HTTPException(status_code=403, detail="Only the Owner can invite an Administrator")
    email = str(payload.email).strip().lower()
    invitation_id = UUID(bytes=secrets.token_bytes(16), version=4)
    token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select name from public.organizations where id = %s", [organization_id])
            organization = cursor.fetchone()
            if organization is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            cursor.execute(
                """
                select 1 from public.profiles
                where lower(email) = %s and id in (
                    select user_id from public.organization_members where organization_id = %s
                )
                limit 1
                """,
                [email, organization_id],
            )
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="This person is already a member of the organisation")
            cursor.execute(
                "delete from public.organization_invitations where organization_id = %s and lower(email) = %s and accepted_at is null and expires_at <= now()",
                [organization_id, email],
            )
            try:
                cursor.execute(
                    """
                    insert into public.organization_invitations
                        (id, organization_id, email, role, invited_by, token_hash, expires_at)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [invitation_id, organization_id, email, payload.role, user_id, token_hash, expires_at],
                )
            except Exception as exc:
                if "organization_invitations_pending_unique" in str(exc):
                    raise HTTPException(status_code=409, detail="There is already a pending invitation for this email") from exc
                raise

    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    if not frontend_url:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.organization_invitations where id = %s", [invitation_id])
        raise HTTPException(status_code=503, detail="Invitation redirect URL is not configured")
    redirect_to = frontend_url + "/accept-invitation?" + urlencode({"invitation_id": str(invitation_id), "token": token})
    email_sent = _supabase_admin_invite(email, redirect_to, organization["name"])
    return {
        "invitation": {"id": str(invitation_id), "email": email, "role": payload.role, "expires_at": expires_at},
        "email_sent": email_sent,
        "invite_url": redirect_to,
    }


@router.post("/invitations/accept")
async def accept_organization_invitation(
    payload: OrganizationInviteAccept,
    email: str = Depends(get_verified_user_email),
    user_id: UUID = Depends(get_current_user_id),
):
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select id, organization_id, email, role
                from public.organization_invitations
                where id = %s and token_hash = %s and lower(email) = %s
                  and accepted_at is null and expires_at > now()
                for update
                """,
                [payload.invitation_id, token_hash, email],
            )
            invitation = cursor.fetchone()
            if invitation is None:
                raise HTTPException(status_code=400, detail="This invitation is invalid, expired, already used or belongs to another email address")
            cursor.execute(
                """
                insert into public.profiles (id, email)
                values (%s, %s)
                on conflict (id) do update set email = excluded.email
                """,
                [user_id, email],
            )
            cursor.execute(
                """
                insert into public.organization_members (organization_id, user_id, role)
                values (%s, %s, %s)
                on conflict (organization_id, user_id) do nothing
                returning user_id
                """,
                [invitation["organization_id"], user_id, invitation["role"]],
            )
            membership_created = cursor.fetchone()
            if membership_created is None:
                raise HTTPException(
                    status_code=409,
                    detail="Your account is already a member of this organisation. Ask an administrator if your access needs to change.",
                )
            cursor.execute(
                "update public.organization_invitations set accepted_at = now(), updated_at = now() where id = %s and accepted_at is null",
                [payload.invitation_id],
            )
            if cursor.rowcount != 1:
                raise HTTPException(status_code=409, detail="This invitation has already been accepted.")

            cursor.execute(
                "select id, name, country_code, timezone from public.organizations where id = %s",
                [invitation["organization_id"]],
            )
            organization = cursor.fetchone()
    return {"organization": organization, "role": invitation["role"]}
