from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import (
    assert_org_permission,
    get_current_user_id,
    get_org_role,
    has_org_permission,
)
from app.db import get_connection

router = APIRouter(prefix="/api/organizations", tags=["organisation permissions"])


class CustomRoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=300)


class RolePermissionsUpdate(BaseModel):
    permissions: dict[str, bool] = Field(min_length=1, max_length=100)


class MemberRoleUpdate(BaseModel):
    role: Literal["admin", "recruiter", "hiring_manager", "viewer"] | None = None
    custom_role_id: UUID | None = None


class MemberPermissionOverrideUpdate(BaseModel):
    effect: Literal["allow", "deny", "inherit"]
    reason: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None


def _audit(cursor, organization_id: UUID, actor_id: UUID, action: str, entity_type: str, entity_id: UUID, metadata: dict):
    import json

    cursor.execute(
        """
        insert into public.audit_events
          (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
        values (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        [organization_id, actor_id, action, entity_type, entity_id, json.dumps(metadata)],
    )


def _assert_can_grant(actor_id: UUID, organization_id: UUID, permission_key: str) -> None:
    actor_role = get_org_role(actor_id, organization_id)
    if actor_role == "owner":
        return
    if permission_key == "ownership.transfer" or not has_org_permission(actor_id, organization_id, permission_key):
        raise HTTPException(
            status_code=403,
            detail=f"Administrators cannot grant a permission they do not hold: {permission_key}",
        )


@router.get("/{organization_id}/permissions")
async def get_organisation_permissions(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.manage_roles")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select permission_key, category, label, description, sensitive
                from public.permission_catalog
                order by category, permission_key
                """
            )
            catalog = list(cursor.fetchall())
            cursor.execute(
                """
                select r.id, r.role_key, r.name, r.description, r.is_system, r.is_active,
                       coalesce(
                         jsonb_object_agg(rp.permission_key, rp.allowed)
                           filter (where rp.permission_key is not null),
                         '{}'::jsonb
                       ) as permissions
                from public.organization_roles r
                left join public.organization_role_permissions rp
                  on rp.organization_id = r.organization_id and rp.role_id = r.id
                where r.organization_id = %s and r.is_active = true
                group by r.id
                order by r.is_system desc, r.name
                """,
                [organization_id],
            )
            roles = list(cursor.fetchall())
    return {"permissions": catalog, "roles": roles}


@router.post("/{organization_id}/roles", status_code=201)
async def create_custom_role(
    organization_id: UUID,
    payload: CustomRoleCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.manage_roles")
    role_id = uuid4()
    role_key = "custom_" + role_id.hex
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.organization_roles
                  (id, organization_id, role_key, name, description, is_system, created_by)
                values (%s, %s, %s, %s, %s, false, %s)
                returning id, role_key, name, description, is_system, is_active
                """,
                [role_id, organization_id, role_key, payload.name.strip(), payload.description, user_id],
            )
            role = cursor.fetchone()
            _audit(cursor, organization_id, user_id, "custom_role_created", "organization_role", role_id,
                   {"role_key": role_key, "name": payload.name.strip()})
    return {"role": role, "permissions": {}}


@router.put("/{organization_id}/roles/{role_id}/permissions")
async def update_role_permissions(
    organization_id: UUID,
    role_id: UUID,
    payload: RolePermissionsUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.manage_roles")
    actor_role = get_org_role(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select role_key, is_system from public.organization_roles where id=%s and organization_id=%s and is_active=true",
                [role_id, organization_id],
            )
            role = cursor.fetchone()
            if role is None:
                raise HTTPException(status_code=404, detail="Role not found")
            if role["role_key"] == "owner" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can change the Owner permission template")
            if role["role_key"] == "admin" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can change the Administrator permission template")

            cursor.execute(
                "select permission_key from public.permission_catalog where permission_key = any(%s)",
                [list(payload.permissions.keys())],
            )
            valid_keys = {row["permission_key"] for row in cursor.fetchall()}
            unknown = sorted(set(payload.permissions) - valid_keys)
            if unknown:
                raise HTTPException(status_code=422, detail={"unknown_permissions": unknown})

            for permission_key, allowed in payload.permissions.items():
                if allowed:
                    _assert_can_grant(user_id, organization_id, permission_key)
                cursor.execute(
                    """
                    insert into public.organization_role_permissions
                      (organization_id, role_id, permission_key, allowed, updated_by, updated_at)
                    values (%s, %s, %s, %s, %s, now())
                    on conflict (role_id, permission_key) do update
                    set allowed=excluded.allowed, updated_by=excluded.updated_by, updated_at=now()
                    """,
                    [organization_id, role_id, permission_key, allowed, user_id],
                )
            _audit(cursor, organization_id, user_id, "role_permissions_updated", "organization_role", role_id,
                   {"changed_permissions": payload.permissions})
    return {"status": "updated", "role_id": str(role_id), "changed": len(payload.permissions)}


@router.patch("/{organization_id}/members/{member_id}/role")
async def update_member_role(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberRoleUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.manage_roles")
    if (payload.role is None) == (payload.custom_role_id is None):
        raise HTTPException(status_code=422, detail="Provide exactly one of role or custom_role_id")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select role from public.organization_members where organization_id=%s and user_id=%s for update",
                [organization_id, member_id],
            )
            target = cursor.fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="Team member not found")
            actor_role = get_org_role(user_id, organization_id)
            if target["role"] in {"owner", "admin"} and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can change an Owner or Administrator membership")
            if payload.role == "admin" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can grant Administrator access")

            if payload.custom_role_id is not None:
                cursor.execute(
                    "select id from public.organization_roles where id=%s and organization_id=%s and is_active=true and is_system=false",
                    [payload.custom_role_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Custom role not found")
                cursor.execute(
                    "update public.organization_members set custom_role_id=%s where organization_id=%s and user_id=%s",
                    [payload.custom_role_id, organization_id, member_id],
                )
                role_value = str(payload.custom_role_id)
            else:
                cursor.execute(
                    "update public.organization_members set role=%s, custom_role_id=null where organization_id=%s and user_id=%s",
                    [payload.role, organization_id, member_id],
                )
                role_value = payload.role
            _audit(cursor, organization_id, user_id, "member_role_updated", "organization_member", member_id,
                   {"previous_role": target["role"], "new_role": role_value})
    return {"status": "updated", "member_id": str(member_id), "role": role_value}


@router.put("/{organization_id}/members/{member_id}/permissions/{permission_key}")
async def update_member_permission_override(
    organization_id: UUID,
    member_id: UUID,
    permission_key: str,
    payload: MemberPermissionOverrideUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.manage_roles")
    actor_role = get_org_role(user_id, organization_id)
    if payload.expires_at is not None:
        if payload.expires_at.tzinfo is None or payload.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="expires_at must be a future timezone-aware datetime")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select role from public.organization_members where organization_id=%s and user_id=%s",
                [organization_id, member_id],
            )
            target = cursor.fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="Team member not found")
            if target["role"] == "owner" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can manage the Owner's access")
            if target["role"] == "admin" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can manage an Administrator's access")
            cursor.execute("select 1 from public.permission_catalog where permission_key=%s", [permission_key])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Permission not found")

            if payload.effect == "inherit":
                cursor.execute(
                    "delete from public.organization_member_permission_overrides where organization_id=%s and user_id=%s and permission_key=%s",
                    [organization_id, member_id, permission_key],
                )
            else:
                if payload.effect == "allow":
                    _assert_can_grant(user_id, organization_id, permission_key)
                cursor.execute(
                    """
                    insert into public.organization_member_permission_overrides
                      (organization_id, user_id, permission_key, effect, reason, expires_at, granted_by, updated_at)
                    values (%s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (organization_id, user_id, permission_key) do update
                    set effect=excluded.effect, reason=excluded.reason, expires_at=excluded.expires_at,
                        granted_by=excluded.granted_by, updated_at=now()
                    """,
                    [organization_id, member_id, permission_key, payload.effect, payload.reason, payload.expires_at, user_id],
                )
            _audit(cursor, organization_id, user_id, "member_permission_override_updated", "organization_member", member_id,
                   {"permission_key": permission_key, "effect": payload.effect,
                    "expires_at": payload.expires_at.isoformat() if payload.expires_at else None})
    return {"status": "updated", "member_id": str(member_id), "permission_key": permission_key, "effect": payload.effect}
