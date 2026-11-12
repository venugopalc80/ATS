import json
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/analytics/reports", tags=["saved analytics reports"])

ReportType = Literal["kpis", "funnel", "workload", "sources", "forecast", "campaign_roi"]


class ReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date | None = None
    date_to: date | None = None
    job_id: UUID | None = None
    recruiter_id: UUID | None = None


class SavedReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    report_type: ReportType
    filters: ReportFilters = Field(default_factory=ReportFilters)
    is_shared: bool = False


class SavedReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    report_type: ReportType | None = None
    filters: ReportFilters | None = None
    is_shared: bool | None = None


def _normalise_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Report name cannot be empty")
    return value


def _normalise_description(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_filters(report_type: str, filters: ReportFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    if report_type in {"workload", "forecast"} and (
        filters.date_from or filters.date_to or filters.job_id
    ):
        raise HTTPException(
            status_code=422,
            detail=f"{report_type} reports do not support date or job filters",
        )


def _filters_json(filters: ReportFilters) -> str:
    return json.dumps(filters.model_dump(exclude_none=True), default=str)


def _public_report(row: dict, can_manage: bool = False) -> dict:
    filters = row.get("filters") or {}
    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "created_by": str(row["created_by"]),
        "name": row["name"],
        "description": row.get("description"),
        "report_type": row["report_type"],
        "filters": filters,
        "is_shared": bool(row["is_shared"]),
        "can_manage": can_manage,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Saved reports are temporarily unavailable")


@router.get("")
async def list_saved_reports(
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    is_admin = get_org_role(user_id, organization_id) in {"owner", "admin"}
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, created_by, name, description,
                              report_type, filters, is_shared, created_at, updated_at
                       from public.saved_report_definitions
                       where organization_id=%s and (is_shared=true or created_by=%s or %s=true)
                       order by updated_at desc, created_at desc""",
                    [organization_id, user_id, is_admin],
                )
                return [_public_report(row, is_admin or row["created_by"] == user_id) for row in cursor.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_unavailable(exc) from exc


@router.post("", status_code=201)
async def create_saved_report(
    organization_id: UUID,
    payload: SavedReportCreate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    name = _normalise_name(payload.name)
    _validate_filters(payload.report_type, payload.filters)
    if payload.is_shared:
        assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.saved_report_definitions
                       (organization_id, created_by, name, description, report_type, filters, is_shared)
                       values (%s,%s,%s,%s,%s,%s::jsonb,%s)
                       returning id, organization_id, created_by, name, description,
                                 report_type, filters, is_shared, created_at, updated_at""",
                    [
                        organization_id, user_id, name, _normalise_description(payload.description),
                        payload.report_type, _filters_json(payload.filters), payload.is_shared,
                    ],
                )
                return _public_report(cursor.fetchone(), can_manage=True)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_unavailable(exc) from exc


@router.get("/{report_id}")
async def get_saved_report(
    report_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    is_admin = get_org_role(user_id, organization_id) in {"owner", "admin"}
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, created_by, name, description,
                              report_type, filters, is_shared, created_at, updated_at
                       from public.saved_report_definitions
                       where id=%s and organization_id=%s
                         and (is_shared=true or created_by=%s or %s=true)""",
                    [report_id, organization_id, user_id, is_admin],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Saved report not found")
                return _public_report(row, can_manage=is_admin or row["created_by"] == user_id)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_unavailable(exc) from exc


@router.patch("/{report_id}")
async def update_saved_report(
    report_id: UUID,
    organization_id: UUID,
    payload: SavedReportUpdate,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    is_admin = get_org_role(user_id, organization_id) in {"owner", "admin"}
    changes = payload.model_dump(exclude_unset=True)
    for required_field in ("name", "report_type", "filters", "is_shared"):
        if required_field in changes and changes[required_field] is None:
            raise HTTPException(status_code=422, detail=f"{required_field} cannot be null")
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, created_by, name, description, report_type, filters, is_shared
                       from public.saved_report_definitions
                       where id=%s and organization_id=%s
                         and (is_shared=true or created_by=%s or %s=true)""",
                    [report_id, organization_id, user_id, is_admin],
                )
                current = cursor.fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Saved report not found")

                is_owner = current["created_by"] == user_id
                if not is_owner:
                    if not is_admin:
                        raise HTTPException(status_code=403, detail="Only the report owner or an organisation admin can edit this report")
                if "is_shared" in changes:
                    assert_org_admin(user_id, organization_id)

                name = _normalise_name(changes.get("name", current["name"]))
                description = _normalise_description(changes.get("description", current["description"]))
                report_type = changes.get("report_type", current["report_type"])
                raw_filters = changes.get("filters", current["filters"] or {})
                filters = raw_filters if isinstance(raw_filters, ReportFilters) else ReportFilters(**raw_filters)
                _validate_filters(report_type, filters)
                is_shared = changes.get("is_shared", current["is_shared"])

                cursor.execute(
                    """update public.saved_report_definitions
                       set name=%s, description=%s, report_type=%s, filters=%s::jsonb,
                           is_shared=%s, updated_at=now()
                       where id=%s and organization_id=%s
                       returning id, organization_id, created_by, name, description,
                                 report_type, filters, is_shared, created_at, updated_at""",
                    [
                        name, description, report_type, _filters_json(filters), is_shared,
                        report_id, organization_id,
                    ],
                )
                return _public_report(cursor.fetchone(), can_manage=True)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_unavailable(exc) from exc


@router.delete("/{report_id}", status_code=204)
async def delete_saved_report(
    report_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    is_admin = get_org_role(user_id, organization_id) in {"owner", "admin"}
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select created_by from public.saved_report_definitions
                       where id=%s and organization_id=%s
                         and (is_shared=true or created_by=%s or %s=true)""",
                    [report_id, organization_id, user_id, is_admin],
                )
                current = cursor.fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Saved report not found")
                if current["created_by"] != user_id:
                    if not is_admin:
                        raise HTTPException(status_code=403, detail="Only the report owner or an organisation admin can delete this report")
                cursor.execute(
                    "delete from public.saved_report_definitions where id=%s and organization_id=%s",
                    [report_id, organization_id],
                )
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_unavailable(exc) from exc
