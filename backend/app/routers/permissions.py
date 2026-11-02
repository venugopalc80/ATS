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


@router.get("/{organization_id}/my-permissions")
async def get_my_organisation_permissions(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select m.role, p.permission_key,
                       case
                         when m.role = 'owner' then true
                         when m.role = 'admin' and p.permission_key = 'ownership.transfer' then false
                         when member_override.effect is not null then member_override.effect = 'allow'
                         else coalesce(role_permission.allowed, false)
                       end as allowed
                from public.organization_members m
                cross join public.permission_catalog p
                left join public.organization_roles role_template
                  on role_template.organization_id = m.organization_id
                 and (
                      (m.custom_role_id is not null and role_template.id = m.custom_role_id)
                      or
                      (m.custom_role_id is null and role_template.role_key = m.role)
                 )
                left join public.organization_role_permissions role_permission
                  on role_permission.organization_id = m.organization_id
                 and role_permission.role_id = role_template.id
                 and role_permission.permission_key = p.permission_key
                left join public.organization_member_permission_overrides member_override
                  on member_override.organization_id = m.organization_id
                 and member_override.user_id = m.user_id
                 and member_override.permission_key = p.permission_key
                 and (member_override.expires_at is null or member_override.expires_at > now())
                where m.organization_id = %s and m.user_id = %s
                order by p.permission_key
                """,
                [organization_id, user_id],
            )
            rows = list(cursor.fetchall())
    if not rows:
        raise HTTPException(status_code=403, detail="You are not a member of this organisation")
    permissions = {row["permission_key"]: bool(row["allowed"]) for row in rows}
    return {"role": rows[0]["role"], "permissions": permissions}


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
            cursor.execute(
                """
                select m.user_id, p.email, p.full_name, m.role, m.custom_role_id,
                       custom_role.name as custom_role_name,
                       coalesce(
                         jsonb_object_agg(
                           overrides.permission_key,
                           jsonb_build_object(
                             'effect', overrides.effect,
                             'reason', overrides.reason,
                             'expires_at', overrides.expires_at
                           )
                         ) filter (where overrides.permission_key is not null),
                         '{}'::jsonb
                       ) as overrides
                from public.organization_members m
                left join public.profiles p on p.id = m.user_id
                left join public.organization_roles custom_role
                  on custom_role.id = m.custom_role_id
                 and custom_role.organization_id = m.organization_id
                left join public.organization_member_permission_overrides overrides
                  on overrides.organization_id = m.organization_id
                 and overrides.user_id = m.user_id
                 and (overrides.expires_at is null or overrides.expires_at > now())
                where m.organization_id = %s
                group by m.user_id, p.email, p.full_name, m.role, m.custom_role_id, custom_role.name
                order by p.full_name nulls last, p.email
                """,
                [organization_id],
            )
            members = list(cursor.fetchall())
    return {"permissions": catalog, "roles": roles, "members": members}


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
            if role["role_key"] == "owner":
                raise HTTPException(status_code=409, detail="The Owner permission template is immutable; ownership always retains full access")
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
            if target["role"] == "owner":
                raise HTTPException(status_code=409, detail="Owner membership can only be changed through the ownership transfer workflow")
            if target["role"] == "admin" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can change an Administrator membership")
            if payload.role == "admin" and actor_role != "owner":
                raise HTTPException(status_code=403, detail="Only the Owner can grant Administrator access")

            if payload.custom_role_id is not None:
                cursor.execute(
                    "select id from public.organization_roles where id=%s and organization_id=%s and is_active=true and is_system=false",
                    [payload.custom_role_id, organization_id],
                )
                selected_role = cursor.fetchone()
                if selected_role is None:
                    raise HTTPException(status_code=404, detail="Custom role not found")
                selected_role_id = selected_role["id"]
                role_value = str(payload.custom_role_id)
            else:
                cursor.execute(
                    "select id from public.organization_roles where organization_id=%s and role_key=%s and is_active=true",
                    [organization_id, payload.role],
                )
                selected_role = cursor.fetchone()
                if selected_role is None:
                    raise HTTPException(status_code=409, detail="The standard role template is not configured")
                selected_role_id = selected_role["id"]
                role_value = payload.role

            if actor_role != "owner":
                cursor.execute(
                    "select permission_key from public.organization_role_permissions where role_id=%s and allowed=true",
                    [selected_role_id],
                )
                for granted in cursor.fetchall():
                    _assert_can_grant(user_id, organization_id, granted["permission_key"])

            if payload.custom_role_id is not None:
                cursor.execute(
                    "update public.organization_members set custom_role_id=%s where organization_id=%s and user_id=%s",
                    [payload.custom_role_id, organization_id, member_id],
                )
            else:
                cursor.execute(
                    "update public.organization_members set role=%s, custom_role_id=null where organization_id=%s and user_id=%s",
                    [payload.role, organization_id, member_id],
                )
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
            if target["role"] == "owner":
                raise HTTPException(status_code=409, detail="Owner access cannot be overridden")
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


# Recruitment teams and resource assignments. These mutations are deliberately
# routed through the authenticated API so every change is audited.
class RecruitmentTeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class TeamMemberChange(BaseModel):
    user_id: UUID


class TeamResourceChange(BaseModel):
    resource_id: UUID


class DirectResourceAssignment(BaseModel):
    user_id: UUID


class MemberAccessScopeUpdate(BaseModel):
    scope: Literal["assigned", "organization"]


def _assert_team_manager(user_id: UUID, organization_id: UUID) -> None:
    assert_org_permission(user_id, organization_id, "team.manage_roles")


@router.get("/{organization_id}/recruitment-teams")
async def list_recruitment_teams(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_permission(user_id, organization_id, "team.read")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select t.id, t.name, t.description, t.created_by, t.created_at, t.updated_at,
                       count(distinct tm.user_id) as member_count,
                       count(distinct tj.job_id) as job_count,
                       count(distinct tc.client_id) as client_count
                from public.recruitment_teams t
                left join public.recruitment_team_members tm
                  on tm.organization_id=t.organization_id and tm.team_id=t.id
                left join public.recruitment_team_jobs tj
                  on tj.organization_id=t.organization_id and tj.team_id=t.id
                left join public.recruitment_team_clients tc
                  on tc.organization_id=t.organization_id and tc.team_id=t.id
                where t.organization_id=%s
                group by t.id
                order by t.name
                """,
                [organization_id],
            )
            teams = list(cursor.fetchall())
    return {"teams": teams}


@router.post("/{organization_id}/recruitment-teams", status_code=201)
async def create_recruitment_team(
    organization_id: UUID,
    payload: RecruitmentTeamCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    team_id = uuid4()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.recruitment_teams
                  (id, organization_id, name, description, created_by)
                values (%s, %s, %s, %s, %s)
                returning id, organization_id, name, description, created_by, created_at
                """,
                [team_id, organization_id, payload.name.strip(), payload.description, user_id],
            )
            team = cursor.fetchone()
            _audit(cursor, organization_id, user_id, "recruitment_team_created",
                   "recruitment_team", team_id, {"name": payload.name.strip()})
    return {"team": team}


@router.patch("/{organization_id}/recruitment-teams/{team_id}")
async def update_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    payload: RecruitmentTeamCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.recruitment_teams
                set name=%s, description=%s, updated_at=now()
                where organization_id=%s and id=%s
                returning id, organization_id, name, description, created_by, created_at, updated_at
                """,
                [payload.name.strip(), payload.description, organization_id, team_id],
            )
            team = cursor.fetchone()
            if team is None:
                raise HTTPException(status_code=404, detail="Recruitment team not found")
            _audit(cursor, organization_id, user_id, "recruitment_team_updated",
                   "recruitment_team", team_id, {"name": payload.name.strip()})
    return {"team": team}


@router.delete("/{organization_id}/recruitment-teams/{team_id}", status_code=204)
async def delete_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "delete from public.recruitment_teams where organization_id=%s and id=%s returning id",
                [organization_id, team_id],
            )
            deleted = cursor.fetchone()
            if deleted is None:
                raise HTTPException(status_code=404, detail="Recruitment team not found")
            _audit(cursor, organization_id, user_id, "recruitment_team_deleted",
                   "recruitment_team", team_id, {})


@router.put("/{organization_id}/recruitment-teams/{team_id}/members")
async def add_recruitment_team_member(
    organization_id: UUID,
    team_id: UUID,
    payload: TeamMemberChange,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from public.recruitment_teams where id=%s and organization_id=%s",
                           [team_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Recruitment team not found")
            cursor.execute("select 1 from public.organization_members where organization_id=%s and user_id=%s",
                           [organization_id, payload.user_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Organisation member not found")
            cursor.execute(
                """
                insert into public.recruitment_team_members (organization_id, team_id, user_id)
                values (%s, %s, %s) on conflict (team_id, user_id) do nothing
                """,
                [organization_id, team_id, payload.user_id],
            )
            _audit(cursor, organization_id, user_id, "recruitment_team_member_added",
                   "recruitment_team", team_id, {"member_user_id": str(payload.user_id)})
    return {"status": "assigned", "team_id": str(team_id), "user_id": str(payload.user_id)}


@router.delete("/{organization_id}/recruitment-teams/{team_id}/members/{member_id}", status_code=204)
async def remove_recruitment_team_member(
    organization_id: UUID,
    team_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                delete from public.recruitment_team_members
                where organization_id=%s and team_id=%s and user_id=%s returning user_id
                """,
                [organization_id, team_id, member_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Team membership not found")
            _audit(cursor, organization_id, user_id, "recruitment_team_member_removed",
                   "recruitment_team", team_id, {"member_user_id": str(member_id)})


@router.put("/{organization_id}/recruitment-teams/{team_id}/jobs")
async def assign_job_to_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    payload: TeamResourceChange,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from public.recruitment_teams where id=%s and organization_id=%s",
                           [team_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Recruitment team not found")
            cursor.execute("select id from public.jobs where id=%s and organization_id=%s",
                           [payload.resource_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Job not found")
            cursor.execute(
                """
                insert into public.recruitment_team_jobs (organization_id, team_id, job_id)
                values (%s, %s, %s) on conflict (team_id, job_id) do nothing
                """,
                [organization_id, team_id, payload.resource_id],
            )
            _audit(cursor, organization_id, user_id, "job_assigned_to_recruitment_team",
                   "job", payload.resource_id, {"team_id": str(team_id)})
    return {"status": "assigned", "team_id": str(team_id), "job_id": str(payload.resource_id)}


@router.delete("/{organization_id}/recruitment-teams/{team_id}/jobs/{job_id}", status_code=204)
async def remove_job_from_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "delete from public.recruitment_team_jobs where organization_id=%s and team_id=%s and job_id=%s returning job_id",
                [organization_id, team_id, job_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Team job assignment not found")
            _audit(cursor, organization_id, user_id, "job_removed_from_recruitment_team",
                   "job", job_id, {"team_id": str(team_id)})


@router.put("/{organization_id}/recruitment-teams/{team_id}/clients")
async def assign_client_to_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    payload: TeamResourceChange,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from public.recruitment_teams where id=%s and organization_id=%s",
                           [team_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Recruitment team not found")
            cursor.execute("select id from public.clients where id=%s and organization_id=%s",
                           [payload.resource_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Client not found")
            cursor.execute(
                """
                insert into public.recruitment_team_clients (organization_id, team_id, client_id)
                values (%s, %s, %s) on conflict (team_id, client_id) do nothing
                """,
                [organization_id, team_id, payload.resource_id],
            )
            _audit(cursor, organization_id, user_id, "client_assigned_to_recruitment_team",
                   "client", payload.resource_id, {"team_id": str(team_id)})
    return {"status": "assigned", "team_id": str(team_id), "client_id": str(payload.resource_id)}


@router.delete("/{organization_id}/recruitment-teams/{team_id}/clients/{client_id}", status_code=204)
async def remove_client_from_recruitment_team(
    organization_id: UUID,
    team_id: UUID,
    client_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "delete from public.recruitment_team_clients where organization_id=%s and team_id=%s and client_id=%s returning client_id",
                [organization_id, team_id, client_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Team client assignment not found")
            _audit(cursor, organization_id, user_id, "client_removed_from_recruitment_team",
                   "client", client_id, {"team_id": str(team_id)})


@router.put("/{organization_id}/candidates/{candidate_id}/assignments")
async def assign_candidate_to_member(
    organization_id: UUID,
    candidate_id: UUID,
    payload: DirectResourceAssignment,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from public.candidates where id=%s and organization_id=%s",
                           [candidate_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Candidate not found")
            cursor.execute("select 1 from public.organization_members where organization_id=%s and user_id=%s",
                           [organization_id, payload.user_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Organisation member not found")
            cursor.execute(
                """
                insert into public.candidate_access_assignments
                  (organization_id, candidate_id, user_id, assigned_by)
                values (%s, %s, %s, %s)
                on conflict (candidate_id, user_id) do nothing
                """,
                [organization_id, candidate_id, payload.user_id, user_id],
            )
            _audit(cursor, organization_id, user_id, "candidate_assigned_to_member",
                   "candidate", candidate_id, {"member_user_id": str(payload.user_id)})
    return {"status": "assigned", "candidate_id": str(candidate_id), "user_id": str(payload.user_id)}


@router.delete("/{organization_id}/candidates/{candidate_id}/assignments/{member_id}", status_code=204)
async def remove_candidate_assignment(
    organization_id: UUID,
    candidate_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                delete from public.candidate_access_assignments
                where organization_id=%s and candidate_id=%s and user_id=%s returning user_id
                """,
                [organization_id, candidate_id, member_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Candidate assignment not found")
            _audit(cursor, organization_id, user_id, "candidate_assignment_removed",
                   "candidate", candidate_id, {"member_user_id": str(member_id)})


@router.put("/{organization_id}/clients/{client_id}/assignments")
async def assign_client_to_member(
    organization_id: UUID,
    client_id: UUID,
    payload: DirectResourceAssignment,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select id from public.clients where id=%s and organization_id=%s",
                           [client_id, organization_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Client not found")
            cursor.execute("select 1 from public.organization_members where organization_id=%s and user_id=%s",
                           [organization_id, payload.user_id])
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Organisation member not found")
            cursor.execute(
                """
                insert into public.client_access_assignments
                  (organization_id, client_id, user_id, assigned_by)
                values (%s, %s, %s, %s)
                on conflict (client_id, user_id) do nothing
                """,
                [organization_id, client_id, payload.user_id, user_id],
            )
            _audit(cursor, organization_id, user_id, "client_assigned_to_member",
                   "client", client_id, {"member_user_id": str(payload.user_id)})
    return {"status": "assigned", "client_id": str(client_id), "user_id": str(payload.user_id)}


@router.delete("/{organization_id}/clients/{client_id}/assignments/{member_id}", status_code=204)
async def remove_client_assignment(
    organization_id: UUID,
    client_id: UUID,
    member_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                delete from public.client_access_assignments
                where organization_id=%s and client_id=%s and user_id=%s returning user_id
                """,
                [organization_id, client_id, member_id],
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Client assignment not found")
            _audit(cursor, organization_id, user_id, "client_assignment_removed",
                   "client", client_id, {"member_user_id": str(member_id)})


@router.put("/{organization_id}/members/{member_id}/access-scope")
async def update_member_access_scope(
    organization_id: UUID,
    member_id: UUID,
    payload: MemberAccessScopeUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    _assert_team_manager(user_id, organization_id)
    actor_role = get_org_role(user_id, organization_id)
    if payload.scope == "organization" and actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only the Owner can grant organisation-wide resource access")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("select role from public.organization_members where organization_id=%s and user_id=%s for update",
                           [organization_id, member_id])
            target = cursor.fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="Organisation member not found")
            if target["role"] == "owner" and payload.scope != "organization":
                raise HTTPException(status_code=409, detail="Owner access cannot be restricted")
            cursor.execute(
                """
                insert into public.organization_member_access_scopes
                  (organization_id, user_id, scope, updated_by, updated_at)
                values (%s, %s, %s, %s, now())
                on conflict (organization_id, user_id) do update
                set scope=excluded.scope, updated_by=excluded.updated_by, updated_at=now()
                """,
                [organization_id, member_id, payload.scope, user_id],
            )
            _audit(cursor, organization_id, user_id, "member_access_scope_updated",
                   "organization_member", member_id, {"scope": payload.scope})
    return {"status": "updated", "member_id": str(member_id), "scope": payload.scope}
