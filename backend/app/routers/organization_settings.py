from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/organizations", tags=["organisation settings"])


class OrganizationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(default="AQERITH", min_length=2, max_length=100)
    default_country_code: str = Field(default="GB", pattern=r"^[A-Z]{2}$")
    default_currency: str = Field(default="GBP", pattern=r"^[A-Z]{3}$")
    timezone: str = "UTC"
    date_format: Literal["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] = "DD/MM/YYYY"
    job_default_work_mode: Literal["onsite", "hybrid", "remote"] = "hybrid"
    job_default_employment_type: Literal["permanent", "contract", "temporary", "internship"] = "permanent"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class OrganizationSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str | None = Field(default=None, min_length=2, max_length=100)
    default_country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    default_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    timezone: str | None = None
    date_format: Literal["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] | None = None
    job_default_work_mode: Literal["onsite", "hybrid", "remote"] | None = None
    job_default_employment_type: Literal["permanent", "contract", "temporary", "internship"] | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


@router.get("/{organization_id}/settings")
async def get_organization_settings(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select version, settings, created_at
                       from public.organization_settings_versions
                       where organization_id=%s
                       order by version desc limit 1""",
                    [organization_id],
                )
                row = cursor.fetchone()
        if row is None:
            return {
                "organization_id": str(organization_id),
                "version": 0,
                "settings": OrganizationSettings().model_dump(),
            }
        settings = OrganizationSettings.model_validate(row["settings"])
        return {
            "organization_id": str(organization_id),
            "version": row["version"],
            "settings": settings.model_dump(),
            "updated_at": row["created_at"],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Settings service is unavailable") from exc


@router.patch("/{organization_id}/settings")
async def update_organization_settings(
    organization_id: UUID,
    payload: OrganizationSettingsPatch,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Provide at least one setting to update")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Serialise writes for an organisation so versions cannot collide.
                cursor.execute("select id from public.organizations where id=%s for update", [organization_id])
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Organisation not found")

                cursor.execute(
                    """select version, settings
                       from public.organization_settings_versions
                       where organization_id=%s
                       order by version desc limit 1""",
                    [organization_id],
                )
                current = cursor.fetchone()
                if current is None:
                    current_settings = OrganizationSettings().model_dump()
                    next_version = 1
                else:
                    current_settings = OrganizationSettings.model_validate(current["settings"]).model_dump()
                    next_version = int(current["version"]) + 1

                current_settings.update(patch)
                try:
                    validated = OrganizationSettings.model_validate(current_settings)
                except ValidationError as exc:
                    raise HTTPException(status_code=422, detail=exc.errors(include_input=False)) from exc

                new_settings = validated.model_dump()
                cursor.execute(
                    """insert into public.organization_settings_versions
                       (organization_id, version, settings, updated_by)
                       values (%s, %s, %s::jsonb, %s)
                       returning id, created_at""",
                    [organization_id, next_version, json.dumps(new_settings), user_id],
                )
                version_row = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                       (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s, %s, 'organization.settings.updated',
                               'organization_settings', %s, %s::jsonb)""",
                    [
                        organization_id,
                        user_id,
                        version_row["id"],
                        json.dumps({
                            "version": next_version,
                            "changed_keys": sorted(patch.keys()),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }),
                    ],
                )
        return {
            "organization_id": str(organization_id),
            "version": next_version,
            "settings": new_settings,
            "updated_at": version_row["created_at"],
        }
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Settings service is unavailable") from exc
