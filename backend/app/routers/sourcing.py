import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api", tags=["search and sourcing"])

RecordType = Literal["candidates", "applications", "jobs", "documents"]
PoolVisibility = Literal["restricted", "organisation"]


class SearchCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str | None = Field(default=None, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=30)
    location: str | None = Field(default=None, max_length=120)
    min_experience: float | None = Field(default=None, ge=0, le=80)
    max_experience: float | None = Field(default=None, ge=0, le=80)
    status: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=80)
    recruiter_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class SavedSearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    name: str = Field(min_length=1, max_length=120)
    record_type: RecordType
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    is_shared: bool = False
    alerts_enabled: bool = False


class SavedSearchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    criteria: SearchCriteria | None = None
    is_shared: bool | None = None
    alerts_enabled: bool | None = None


class CandidateTagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    name: str = Field(min_length=1, max_length=60)
    colour: str = Field(default="#64748b", pattern=r"^#[0-9A-Fa-f]{6}$")


class PoolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    owner_user_id: UUID | None = None
    visibility: PoolVisibility = "restricted"


class PoolMembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    candidate_id: UUID
    purpose: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    target_job_id: UUID | None = None
    owner_user_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    budget_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    attribution_window_days: int = Field(default=30, ge=1, le=365)


class CampaignChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    channel_key: Literal["employee_referral", "careers_site", "linkedin", "job_board", "agency", "event", "email", "social", "other"]
    source_label: str | None = Field(default=None, max_length=160)
    external_reference: str | None = Field(default=None, max_length=500)
    spend_amount: float | None = Field(default=None, ge=0)


class ReferralCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    campaign_id: UUID | None = None
    channel_id: UUID | None = None
    candidate_id: UUID | None = None
    application_id: UUID | None = None
    referrer_user_id: UUID | None = None
    referrer_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class ReferralStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    status: Literal["received", "reviewing", "qualified", "interviewing", "hired", "declined", "withdrawn"]
    reason: str = Field(min_length=1, max_length=500)


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Search and sourcing service is unavailable")


def _escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def _search_rows(organization_id: UUID, record_type: RecordType, criteria: SearchCriteria, limit: int, offset: int):
    where = ["base.organization_id = %s"]
    params: list[object] = [organization_id]
    joins = ""
    if record_type == "candidates":
        select = """select base.id, 'candidate' as record_type, base.first_name, base.last_name,
          base.current_title as title, base.city, base.region, base.country_code, base.status,
          base.years_experience, base.skills, base.created_at"""
        source = "public.candidates base"
        if criteria.q:
            where.append("(base.first_name ilike %s escape '!' or coalesce(base.last_name,'') ilike %s escape '!' or coalesce(base.current_title,'') ilike %s escape '!' or coalesce(base.city,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term] * 4)
        if criteria.skills:
            where.append("base.skills && %s::text[]")
            params.append(criteria.skills)
        if criteria.location:
            where.append("(coalesce(base.city,'') ilike %s escape '!' or coalesce(base.region,'') ilike %s escape '!' or coalesce(base.country_code,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.location.strip()) + "%"
            params.extend([term] * 3)
        if criteria.min_experience is not None:
            where.append("base.years_experience >= %s"); params.append(criteria.min_experience)
        if criteria.max_experience is not None:
            where.append("base.years_experience <= %s"); params.append(criteria.max_experience)
        if criteria.status:
            where.append("base.status = %s"); params.append(criteria.status)
    elif record_type == "applications":
        joins = """ join public.candidates c on c.id=base.candidate_id and c.organization_id=base.organization_id
                    join public.jobs j on j.id=base.job_id and j.organization_id=base.organization_id """
        select = """select base.id, 'application' as record_type, base.candidate_id, base.job_id,
          concat_ws(' ',c.first_name,c.last_name) as candidate_name, j.title as job_title,
          base.status, base.source, base.created_at"""
        source = "public.applications base"
        if criteria.q:
            where.append("(concat_ws(' ',c.first_name,c.last_name) ilike %s escape '!' or coalesce(j.title,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term, term])
        if criteria.status:
            where.append("base.status = %s"); params.append(criteria.status)
        if criteria.source:
            where.append("base.source = %s"); params.append(criteria.source)
        if criteria.recruiter_id:
            where.append("j.recruiter_id = %s"); params.append(criteria.recruiter_id)
        if criteria.location:
            where.append("(coalesce(j.location,'') ilike %s escape '!' or coalesce(j.country_code,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.location.strip()) + "%"
            params.extend([term, term])
        if criteria.skills:
            where.append("j.required_skills && %s::text[]"); params.append(criteria.skills)
    elif record_type == "jobs":
        select = """select base.id, 'job' as record_type, base.title, base.location, base.country_code,
          base.status, base.recruiter_id, base.required_skills as skills, base.experience_min,
          base.experience_max, base.created_at"""
        source = "public.jobs base"
        if criteria.q:
            where.append("(base.title ilike %s escape '!' or coalesce(base.location,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term, term])
        if criteria.status:
            where.append("base.status = %s"); params.append(criteria.status)
        if criteria.recruiter_id:
            where.append("base.recruiter_id = %s"); params.append(criteria.recruiter_id)
        if criteria.location:
            where.append("(coalesce(base.location,'') ilike %s escape '!' or coalesce(base.country_code,'') ilike %s escape '!')")
            term = "%" + _escape_like(criteria.location.strip()) + "%"
            params.extend([term, term])
        if criteria.skills:
            where.append("base.required_skills && %s::text[]"); params.append(criteria.skills)
        if criteria.min_experience is not None:
            where.append("coalesce(base.experience_max, base.experience_min, 0) >= %s"); params.append(criteria.min_experience)
        if criteria.max_experience is not None:
            where.append("coalesce(base.experience_min, base.experience_max, 0) <= %s"); params.append(criteria.max_experience)
    else:
        joins = " join public.candidates c on c.id=base.candidate_id and c.organization_id=base.organization_id "
        select = """select base.id, 'document' as record_type, base.candidate_id, base.document_type,
          base.original_filename, base.content_type, base.created_at,
          concat_ws(' ',c.first_name,c.last_name) as candidate_name"""
        source = "public.candidate_documents base"
        where.append("base.deleted_at is null")
        if criteria.q:
            where.append("(base.original_filename ilike %s escape '!' or concat_ws(' ',c.first_name,c.last_name) ilike %s escape '!')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term, term])
    if criteria.date_from:
        where.append("base.created_at >= %s"); params.append(criteria.date_from)
    if criteria.date_to:
        where.append("base.created_at < %s"); params.append(criteria.date_to)
    if criteria.min_experience is not None and record_type not in ("candidates", "jobs"):
        raise HTTPException(status_code=422, detail="Experience filters apply to candidates and jobs only")
    if criteria.max_experience is not None and record_type not in ("candidates", "jobs"):
        raise HTTPException(status_code=422, detail="Experience filters apply to candidates and jobs only")
    sql = select + " from " + source + joins + " where " + " and ".join(where) + " order by base.created_at desc limit %s offset %s"
    params.extend([limit, offset])
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


@router.get("/search")
async def advanced_search(
    organization_id: UUID,
    record_type: RecordType,
    q: str | None = Query(default=None, max_length=100),
    skills: list[str] = Query(default=[]),
    location: str | None = Query(default=None, max_length=120),
    min_experience: float | None = Query(default=None, ge=0, le=80),
    max_experience: float | None = Query(default=None, ge=0, le=80),
    status: str | None = Query(default=None, max_length=40),
    source: str | None = Query(default=None, max_length=80),
    recruiter_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    if min_experience is not None and max_experience is not None and min_experience > max_experience:
        raise HTTPException(status_code=422, detail="Minimum experience cannot exceed maximum experience")
    if date_from and date_to and date_from >= date_to:
        raise HTTPException(status_code=422, detail="date_from must be earlier than date_to")
    criteria = SearchCriteria(q=q, skills=skills, location=location, min_experience=min_experience,
                              max_experience=max_experience, status=status, source=source,
                              recruiter_id=recruiter_id, date_from=date_from, date_to=date_to)
    try:
        rows = _search_rows(organization_id, record_type, criteria, limit, offset)
        return {"items": rows, "limit": limit, "offset": offset, "record_type": record_type}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/saved-searches")
async def list_saved_searches(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select id, organization_id, owner_user_id, name, record_type,
                    criteria_version, criteria, is_shared, alerts_enabled, created_at, updated_at
                    from public.saved_searches where organization_id=%s
                    and (owner_user_id=%s or is_shared=true) order by updated_at desc""",
                    [organization_id, user_id])
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/saved-searches", status_code=201)
async def create_saved_search(payload: SavedSearchCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    if payload.is_shared:
        assert_org_admin(user_id, payload.organization_id)
    try:
        criteria = payload.criteria.model_dump(mode="json", exclude_none=True)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.saved_searches
                    (organization_id,owner_user_id,name,record_type,criteria_version,criteria,is_shared,alerts_enabled)
                    values (%s,%s,%s,%s,1,%s::jsonb,%s,%s)
                    returning id, organization_id, owner_user_id, name, record_type, criteria_version,
                    criteria, is_shared, alerts_enabled, created_at, updated_at""",
                    [payload.organization_id,user_id,payload.name.strip(),payload.record_type,
                     json.dumps(criteria),payload.is_shared,payload.alerts_enabled])
                row = cursor.fetchone()
        return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.patch("/saved-searches/{search_id}")
async def update_saved_search(search_id: UUID, organization_id: UUID, payload: SavedSearchUpdate,
                              user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    if "is_shared" in data and data["is_shared"] is not None:
        assert_org_admin(user_id, organization_id)
    if "criteria" in data and data["criteria"] is not None:
        data["criteria"] = json.dumps(data["criteria"].model_dump(mode="json", exclude_none=True))
    assignments = []
    values: list[object] = []
    for key in ("name", "criteria", "is_shared", "alerts_enabled"):
        if key in data and data[key] is not None:
            assignments.append(key + " = %s" + ("::jsonb" if key == "criteria" else ""))
            values.append(data[key])
    if not assignments:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    assignments.append("updated_at = now()")
    values.extend([search_id, organization_id, user_id])
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("update public.saved_searches set " + ", ".join(assignments) +
                    " where id=%s and organization_id=%s and owner_user_id=%s returning id, name, record_type, criteria_version, criteria, is_shared, alerts_enabled, updated_at", values)
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/saved-searches/{search_id}/results")
async def run_saved_search(search_id: UUID, organization_id: UUID,
                           limit: int = Query(default=25, ge=1, le=100),
                           offset: int = Query(default=0, ge=0, le=100000),
                           user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select record_type, criteria from public.saved_searches
                    where id=%s and organization_id=%s and (owner_user_id=%s or is_shared=true)""",
                    [search_id, organization_id, user_id])
                saved = cursor.fetchone()
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        criteria = SearchCriteria.model_validate(saved["criteria"])
        rows = _search_rows(organization_id, saved["record_type"], criteria, limit, offset)
        return {"items": rows, "limit": limit, "offset": offset, "record_type": saved["record_type"]}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Saved search criteria are invalid; edit and save the filter again") from exc


@router.delete("/saved-searches/{search_id}", status_code=204)
async def delete_saved_search(search_id: UUID, organization_id: UUID,
                              user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.saved_searches where id=%s and organization_id=%s and owner_user_id=%s",
                               [search_id, organization_id, user_id])
                if cursor.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Saved search not found")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/talent-pools")
async def list_talent_pools(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select p.id,p.organization_id,p.name,p.description,p.owner_user_id,p.visibility,
                    p.created_by,p.created_at,p.updated_at,count(m.id) filter (where m.status='active') as member_count
                    from public.talent_pools p left join public.talent_pool_memberships m
                    on m.organization_id=p.organization_id and m.pool_id=p.id
                    where p.organization_id=%s and (p.visibility='organisation' or p.owner_user_id=%s or p.created_by=%s)
                    group by p.id order by p.updated_at desc""", [organization_id,user_id,user_id])
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/talent-pools", status_code=201)
async def create_talent_pool(payload: PoolCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    owner = payload.owner_user_id or user_id
    if owner != user_id:
        assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.talent_pools
                    (organization_id,name,description,owner_user_id,visibility,created_by)
                    values (%s,%s,%s,%s,%s,%s)
                    returning id,organization_id,name,description,owner_user_id,visibility,created_by,created_at,updated_at""",
                    [payload.organization_id,payload.name.strip(),payload.description,owner,payload.visibility,user_id])
                return cursor.fetchone()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A talent pool with this name already exists") from exc
        raise


@router.get("/talent-pools/{pool_id}/members")
async def list_talent_pool_members(pool_id: UUID, organization_id: UUID,
                                   include_inactive: bool = False,
                                   user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select owner_user_id,visibility,created_by from public.talent_pools where id=%s and organization_id=%s",
                               [pool_id,organization_id])
                pool = cursor.fetchone()
                if not pool:
                    raise HTTPException(status_code=404, detail="Talent pool not found")
                if pool["visibility"] == "restricted" and pool["owner_user_id"] != user_id and pool["created_by"] != user_id:
                    assert_org_admin(user_id, organization_id)
                sql = """select m.id,m.candidate_id,m.status,m.purpose,m.added_by,m.added_at,m.expires_at,m.removed_at,
                    c.first_name,c.last_name,c.current_title,c.city,c.region,c.country_code,c.status as candidate_status
                    from public.talent_pool_memberships m join public.candidates c
                    on c.id=m.candidate_id and c.organization_id=m.organization_id
                    where m.organization_id=%s and m.pool_id=%s"""
                params: list[object] = [organization_id,pool_id]
                if not include_inactive:
                    sql += " and m.status='active' and (m.expires_at is null or m.expires_at > now())"
                sql += " order by m.added_at desc"
                cursor.execute(sql, params)
                return list(cursor.fetchall())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/talent-pools/{pool_id}/members", status_code=201)
async def add_talent_pool_member(pool_id: UUID, payload: PoolMembershipCreate,
                                 user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    if payload.expires_at and payload.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Membership expiry must be in the future")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select id,owner_user_id,visibility,created_by from public.talent_pools where id=%s and organization_id=%s",
                               [pool_id,payload.organization_id])
                pool = cursor.fetchone()
                if not pool:
                    raise HTTPException(status_code=404, detail="Talent pool not found")
                if pool["visibility"] == "restricted" and pool["owner_user_id"] != user_id and pool["created_by"] != user_id:
                    assert_org_admin(user_id, payload.organization_id)
                cursor.execute("""select id,status,retention_until from public.candidates
                    where id=%s and organization_id=%s""", [payload.candidate_id,payload.organization_id])
                candidate = cursor.fetchone()
                if not candidate:
                    raise HTTPException(status_code=404, detail="Candidate not found")
                if candidate["status"] == "do_not_contact":
                    raise HTTPException(status_code=409, detail="Candidates marked do_not_contact cannot be added to a future-contact pool")
                if candidate["retention_until"] and candidate["retention_until"] <= datetime.now(timezone.utc):
                    raise HTTPException(status_code=409, detail="Candidate retention period has expired")
                cursor.execute("""insert into public.talent_pool_memberships
                    (organization_id,pool_id,candidate_id,added_by,purpose,expires_at,status)
                    values (%s,%s,%s,%s,%s,%s,'active')
                    on conflict do nothing
                    returning id,organization_id,pool_id,candidate_id,status,added_by,purpose,added_at,expires_at""",
                    [payload.organization_id,pool_id,payload.candidate_id,user_id,payload.purpose.strip(),payload.expires_at])
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=409, detail="Candidate is already an active member of this pool")
                cursor.execute("""insert into public.talent_pool_membership_events
                    (organization_id,membership_id,actor_user_id,event_type,reason)
                    values (%s,%s,%s,'added',%s)""",
                    [payload.organization_id,row["id"],user_id,payload.purpose.strip()])
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'talent_pool_member_added','talent_pool_membership',%s,%s::jsonb)""",
                    [payload.organization_id,user_id,row["id"],json.dumps({"pool_id":str(pool_id),"candidate_id":str(payload.candidate_id)})])
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.delete("/talent-pools/{pool_id}/members/{membership_id}", status_code=204)
async def remove_talent_pool_member(pool_id: UUID, membership_id: UUID, organization_id: UUID,
                                    reason: str = Query(min_length=1, max_length=500),
                                    user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""update public.talent_pool_memberships m set status='removed',removed_at=now(),updated_at=now()
                    from public.talent_pools p where m.id=%s and m.pool_id=%s and m.organization_id=%s
                    and p.id=m.pool_id and p.organization_id=m.organization_id
                    and m.status='active' and (p.visibility='organisation' or p.owner_user_id=%s or p.created_by=%s)
                    returning m.id""", [membership_id,pool_id,organization_id,user_id,user_id])
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Active pool membership not found or access denied")
                cursor.execute("""insert into public.talent_pool_membership_events
                    (organization_id,membership_id,actor_user_id,event_type,reason) values (%s,%s,%s,'removed',%s)""",
                    [organization_id,membership_id,user_id,reason.strip()])
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'talent_pool_member_removed','talent_pool_membership',%s,%s::jsonb)""",
                    [organization_id,user_id,membership_id,json.dumps({"pool_id":str(pool_id),"reason":reason.strip()})])
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


CSV_MAX_BYTES = 5 * 1024 * 1024
CSV_MAX_ROWS = 1000
CANDIDATE_IMPORT_FIELDS = {
    "first_name", "last_name", "email", "phone", "city", "region",
    "country_code", "current_title", "years_experience", "skills", "status",
}
CSV_HEADER_ALIASES = {
    "first_name": ("first name", "firstname", "given name", "forename"),
    "last_name": ("last name", "lastname", "surname", "family name"),
    "email": ("email", "email address", "e-mail"),
    "phone": ("phone", "phone number", "mobile", "telephone"),
    "city": ("city", "town"),
    "region": ("region", "state", "county", "province"),
    "country_code": ("country code", "country", "country_code"),
    "current_title": ("current title", "job title", "current role", "title"),
    "years_experience": ("years experience", "years of experience", "experience", "years_experience"),
    "skills": ("skills", "skill set", "technologies"),
    "status": ("status", "candidate status"),
}


def _normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _default_column_mapping(headers: list[str]) -> dict[str, str]:
    normalized = {_normalise_header(header): header for header in headers}
    mapping: dict[str, str] = {}
    for field, aliases in CSV_HEADER_ALIASES.items():
        for alias in aliases:
            if _normalise_header(alias) in normalized:
                mapping[field] = normalized[_normalise_header(alias)]
                break
    return mapping


def _map_csv_row(row: dict[str, str | None], mapping: dict[str, str]) -> tuple[dict, list[str]]:
    data: dict[str, object] = {}
    errors: list[str] = []
    field_limits = {"first_name": 100, "last_name": 100, "email": 320, "phone": 50, "city": 120, "region": 120, "country_code": 2, "current_title": 200}
    for field, header in mapping.items():
        raw = (row.get(header) or "").strip()
        if field == "skills":
            data[field] = [item.strip()[:80] for item in re.split(r"[,;|]", raw) if item.strip()][:50]
        elif field == "country_code":
            data[field] = raw.upper() or None
        elif field == "email":
            data[field] = raw.lower() or None
        elif field == "years_experience":
            if not raw:
                data[field] = None
            else:
                try:
                    value = float(raw)
                    if value < 0 or value > 80:
                        raise ValueError
                    data[field] = value
                except ValueError:
                    errors.append("years_experience must be a number between 0 and 80")
        elif field == "status":
            value = raw.casefold().replace(" ", "_") or "active"
            if value not in {"active", "inactive", "placed", "do_not_contact"}:
                errors.append("status must be active, inactive, placed or do_not_contact")
            else:
                data[field] = value
        else:
            data[field] = raw[:field_limits.get(field, 320)] or None
    data.setdefault("first_name", None)
    data.setdefault("last_name", None)
    data.setdefault("email", None)
    data.setdefault("phone", None)
    data.setdefault("city", None)
    data.setdefault("region", None)
    data.setdefault("country_code", None)
    data.setdefault("current_title", None)
    data.setdefault("years_experience", None)
    data.setdefault("skills", [])
    data.setdefault("status", "active")
    if not data["first_name"]:
        errors.append("first_name is required")
    if data["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(data["email"])):
        errors.append("email format is invalid")
    if data["country_code"] and not re.fullmatch(r"[A-Z]{2}", str(data["country_code"])):
        errors.append("country_code must be a two-letter ISO code")
    return data, errors


@router.post("/imports/preview", status_code=201)
async def preview_candidate_csv_import(
    organization_id: UUID,
    file: UploadFile = File(...),
    column_mapping: str | None = Query(default=None, max_length=3000),
    user_id: UUID = Depends(get_current_user_id),
):
    """Validate a bounded CSV, persist row-level preview results, and do not create candidates yet."""
    assert_org_member(user_id, organization_id)
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only CSV imports are supported by this endpoint")
    if (file.content_type or "").lower() not in {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Unsupported CSV content type")
    raw = await file.read(CSV_MAX_BYTES + 1)
    await file.close()
    if not raw:
        raise HTTPException(status_code=422, detail="The uploaded CSV is empty")
    if len(raw) > CSV_MAX_BYTES:
        raise HTTPException(status_code=413, detail="CSV files must be 5 MB or smaller")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        headers = reader.fieldnames or []
        if not headers or len(headers) > 100:
            raise HTTPException(status_code=422, detail="CSV must contain between 1 and 100 header columns")
        if any(not header or len(header) > 200 for header in headers):
            raise HTTPException(status_code=422, detail="CSV contains an invalid header")
        if column_mapping:
            try:
                supplied_mapping = json.loads(column_mapping)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=422, detail="column_mapping must be valid JSON") from exc
            if not isinstance(supplied_mapping, dict) or any(
                key not in CANDIDATE_IMPORT_FIELDS or value not in headers
                for key, value in supplied_mapping.items()
            ):
                raise HTTPException(status_code=422, detail="Column mapping contains an unsupported field or unknown CSV header")
            mapping = supplied_mapping
        else:
            mapping = _default_column_mapping(headers)
        if "first_name" not in mapping:
            raise HTTPException(status_code=422, detail="Map a CSV column to first_name before previewing")
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if row_number > CSV_MAX_ROWS + 1:
                raise HTTPException(status_code=413, detail=f"CSV imports are limited to {CSV_MAX_ROWS} data rows per batch")
            rows.append((row_number, row))
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail="CSV parsing failed") from exc

    file_digest = hashlib.sha256(raw).hexdigest()
    seen_emails: set[str] = set()
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.candidate_sources (organization_id,source_key,display_name,source_type)
                    values (%s,'csv_import','CSV import','csv_import')
                    on conflict (organization_id,source_key) do update set display_name=excluded.display_name
                    returning id""", [organization_id])
                source_id = cursor.fetchone()["id"]
                cursor.execute("""insert into public.import_batches
                    (organization_id,source_id,uploaded_by,original_filename,content_type,file_size_bytes,file_sha256,status,total_rows)
                    values (%s,%s,%s,%s,%s,%s,%s,'previewed',%s)
                    returning id""",
                    [organization_id,source_id,user_id,filename[:255],file.content_type or "text/csv",len(raw),file_digest,len(rows)])
                batch_id = cursor.fetchone()["id"]
                valid_count = duplicate_count = rejected_count = 0
                for row_number, raw_row in rows:
                    mapped, errors = _map_csv_row(raw_row, mapping)
                    email = mapped.get("email")
                    duplicate_id = None
                    status_value = "valid"
                    if email:
                        normalized_email = str(email).casefold()
                        if normalized_email in seen_emails:
                            errors.append("Duplicate email appears earlier in this import batch")
                            status_value = "duplicate"
                        else:
                            seen_emails.add(normalized_email)
                            cursor.execute("""select id from public.candidates
                                where organization_id=%s and lower(email)=lower(%s) limit 1""",
                                [organization_id, email])
                            existing = cursor.fetchone()
                            if existing:
                                duplicate_id = existing["id"]
                                errors.append("A candidate with this email already exists")
                                status_value = "duplicate"
                    if errors and status_value != "duplicate":
                        status_value = "rejected"
                    if status_value == "valid":
                        valid_count += 1
                    elif status_value == "duplicate":
                        duplicate_count += 1
                    else:
                        rejected_count += 1
                    cursor.execute("""insert into public.import_row_results
                        (organization_id,batch_id,row_number,status,mapped_data,errors,duplicate_candidate_id)
                        values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
                        [organization_id,batch_id,row_number,status_value,json.dumps(mapped),json.dumps(errors),duplicate_id])
                cursor.execute("""update public.import_batches set valid_rows=%s,duplicate_rows=%s,rejected_rows=%s,
                    updated_at=now() where id=%s and organization_id=%s""",
                    [valid_count,duplicate_count,rejected_count,batch_id,organization_id])
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'candidate_csv_import_previewed','import_batch',%s,%s::jsonb)""",
                    [organization_id,user_id,batch_id,json.dumps({"filename":filename[:255],"sha256":file_digest,"rows":len(rows)})])
                return {"batch_id":batch_id,"filename":filename[:255],"sha256":file_digest,
                    "total_rows":len(rows),"valid_rows":valid_count,"duplicate_rows":duplicate_count,
                    "rejected_rows":rejected_count,"column_mapping":mapping,
                    "message":"Preview saved. No candidate records have been created yet."}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/imports/{batch_id}/commit")
async def commit_candidate_csv_import(
    batch_id: UUID,
    organization_id: UUID,
    duplicate_policy: Literal["review", "skip", "allow"] = "review",
    user_id: UUID = Depends(get_current_user_id),
):
    """Commit only reviewed preview rows; each created candidate retains source and batch provenance."""
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select id,source_id,status,total_rows from public.import_batches
                    where id=%s and organization_id=%s for update""", [batch_id,organization_id])
                batch = cursor.fetchone()
                if not batch:
                    raise HTTPException(status_code=404, detail="Import batch not found")
                if batch["status"] != "previewed":
                    raise HTTPException(status_code=409, detail="This import batch has already been committed or cannot be committed in its current state")
                cursor.execute("""select id,row_number,status,mapped_data,duplicate_candidate_id
                    from public.import_row_results where organization_id=%s and batch_id=%s
                    order by row_number for update""", [organization_id,batch_id])
                row_results = list(cursor.fetchall())
                imported = duplicates = rejected = 0
                for item in row_results:
                    should_import = item["status"] == "valid" or (item["status"] == "duplicate" and duplicate_policy == "allow")
                    if item["status"] == "duplicate":
                        duplicates += 1
                    if item["status"] == "rejected":
                        rejected += 1
                    if not should_import:
                        continue
                    data = item["mapped_data"]
                    cursor.execute("""insert into public.candidates
                        (organization_id,first_name,last_name,email,phone,city,region,country_code,status,
                         current_title,years_experience,skills,source_id,import_batch_id,created_at,updated_at)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
                        returning id""",
                        [organization_id,data["first_name"],data.get("last_name"),data.get("email"),data.get("phone"),
                         data.get("city"),data.get("region"),data.get("country_code"),data.get("status","active"),
                         data.get("current_title"),data.get("years_experience"),data.get("skills",[]),batch["source_id"],batch_id])
                    candidate_id = cursor.fetchone()["id"]
                    cursor.execute("""update public.import_row_results set status='imported',candidate_id=%s,processed_at=now()
                        where id=%s and organization_id=%s""", [candidate_id,item["id"],organization_id])
                    cursor.execute("""insert into public.audit_events
                        (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                        values (%s,%s,'candidate_imported_from_csv','candidate',%s,%s::jsonb)""",
                        [organization_id,user_id,candidate_id,json.dumps({"batch_id":str(batch_id),"row_number":item["row_number"]})])
                    imported += 1
                final_status = "completed" if rejected == 0 and duplicates == 0 else "completed_with_errors"
                cursor.execute("""update public.import_batches set status=%s,duplicate_policy=%s,imported_rows=%s,
                    duplicate_rows=%s,rejected_rows=%s,completed_at=now(),updated_at=now()
                    where id=%s and organization_id=%s returning id,status,total_rows,imported_rows,duplicate_rows,rejected_rows""",
                    [final_status,duplicate_policy,imported,duplicates,rejected,batch_id,organization_id])
                summary = cursor.fetchone()
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'candidate_csv_import_committed','import_batch',%s,%s::jsonb)""",
                    [organization_id,user_id,batch_id,json.dumps({"duplicate_policy":duplicate_policy,"imported":imported,"duplicates":duplicates,"rejected":rejected})])
                return summary
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/imports")
async def list_candidate_import_batches(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select id,source_id,uploaded_by,original_filename,content_type,file_size_bytes,
                    file_sha256,status,duplicate_policy,total_rows,valid_rows,imported_rows,duplicate_rows,
                    rejected_rows,created_at,started_at,completed_at,updated_at
                    from public.import_batches where organization_id=%s order by created_at desc limit 100""",
                    [organization_id])
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/candidate-tags")
async def list_candidate_tags(organization_id: UUID, candidate_id: UUID | None = None,
                              user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if candidate_id:
                    cursor.execute("select id from public.candidates where id=%s and organization_id=%s",
                                   [candidate_id,organization_id])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Candidate not found")
                    cursor.execute("""select t.id,t.organization_id,t.name,t.colour,t.created_by,t.created_at,
                        (a.candidate_id is not null) as assigned
                        from public.candidate_tags t left join public.candidate_tag_assignments a
                        on a.organization_id=t.organization_id and a.tag_id=t.id and a.candidate_id=%s
                        where t.organization_id=%s order by t.name""", [candidate_id,organization_id])
                else:
                    cursor.execute("""select id,organization_id,name,colour,created_by,created_at
                        from public.candidate_tags where organization_id=%s order by name""", [organization_id])
                return list(cursor.fetchall())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/candidate-tags", status_code=201)
async def create_candidate_tag(payload: CandidateTagCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.candidate_tags (organization_id,name,colour,created_by)
                    values (%s,%s,%s,%s) returning id,organization_id,name,colour,created_by,created_at""",
                    [payload.organization_id,payload.name.strip(),payload.colour,user_id])
                return cursor.fetchone()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A tag with this name already exists") from exc
        raise


@router.put("/candidate-tags/{tag_id}/candidates/{candidate_id}")
async def assign_candidate_tag(tag_id: UUID, candidate_id: UUID, organization_id: UUID,
                               user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.candidate_tag_assignments
                    (organization_id,candidate_id,tag_id,assigned_by) select %s,c.id,t.id,%s
                    from public.candidates c join public.candidate_tags t
                      on t.id=%s and t.organization_id=c.organization_id
                    where c.id=%s and c.organization_id=%s
                    on conflict (organization_id,candidate_id,tag_id) do nothing
                    returning organization_id,candidate_id,tag_id,assigned_by,created_at""",
                    [organization_id,user_id,tag_id,candidate_id,organization_id])
                row = cursor.fetchone()
                if row is None:
                    cursor.execute("""select 1 from public.candidate_tag_assignments
                        where organization_id=%s and candidate_id=%s and tag_id=%s""",
                        [organization_id,candidate_id,tag_id])
                    if cursor.fetchone():
                        raise HTTPException(status_code=409, detail="Tag is already assigned to this candidate")
                    raise HTTPException(status_code=404, detail="Candidate or tag not found")
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'candidate_tag_assigned','candidate',%s,%s::jsonb)""",
                    [organization_id,user_id,candidate_id,json.dumps({"tag_id":str(tag_id)})])
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.delete("/candidate-tags/{tag_id}/candidates/{candidate_id}", status_code=204)
async def unassign_candidate_tag(tag_id: UUID, candidate_id: UUID, organization_id: UUID,
                                 user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""delete from public.candidate_tag_assignments
                    where organization_id=%s and candidate_id=%s and tag_id=%s""",
                    [organization_id,candidate_id,tag_id])
                if cursor.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Tag assignment not found")
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'candidate_tag_unassigned','candidate',%s,%s::jsonb)""",
                    [organization_id,user_id,candidate_id,json.dumps({"tag_id":str(tag_id)})])
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/campaigns")
async def list_campaigns(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select c.id,c.organization_id,c.name,c.description,c.status,c.target_job_id,
                    c.owner_user_id,c.starts_at,c.ends_at,c.budget_amount,c.budget_currency,c.attribution_window_days,
                    c.created_at,c.updated_at,count(distinct cm.candidate_id) as attributed_candidates,
                    count(distinct r.id) as referrals,
                    count(distinct r.id) filter (where r.status='qualified') as qualified_referrals,
                    count(distinct r.id) filter (where r.status='hired') as hired_referrals,
                    c.budget_amount / nullif(count(distinct r.id) filter (where r.status='hired'),0) as budget_per_hire
                    from public.recruitment_campaigns c
                    left join public.campaign_memberships cm on cm.organization_id=c.organization_id and cm.campaign_id=c.id
                    left join public.referrals r on r.organization_id=c.organization_id and r.campaign_id=c.id
                    where c.organization_id=%s
                    group by c.id order by c.created_at desc""", [organization_id])
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/campaigns", status_code=201)
async def create_campaign(payload: CampaignCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    if payload.ends_at and payload.starts_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="Campaign end must be after its start")
    if (payload.budget_amount is None) != (payload.budget_currency is None):
        raise HTTPException(status_code=422, detail="Budget amount and currency must be supplied together")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.recruitment_campaigns
                    (organization_id,name,description,target_job_id,owner_user_id,starts_at,ends_at,budget_amount,budget_currency,attribution_window_days,created_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    returning id,organization_id,name,description,status,target_job_id,owner_user_id,starts_at,ends_at,budget_amount,budget_currency,attribution_window_days,created_at,updated_at""",
                    [payload.organization_id,payload.name.strip(),payload.description,payload.target_job_id,
                     payload.owner_user_id or user_id,payload.starts_at,payload.ends_at,payload.budget_amount,
                     payload.budget_currency,payload.attribution_window_days,user_id])
                row = cursor.fetchone()
                cursor.execute("""insert into public.campaign_events
                    (organization_id,campaign_id,actor_user_id,event_type,new_value)
                    values (%s,%s,%s,'created',%s::jsonb)""",
                    [payload.organization_id,row["id"],user_id,json.dumps({"name":payload.name.strip()})])
                return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Campaign could not be created; check the target job and supplied fields") from exc


@router.get("/campaigns/{campaign_id}/channels")
async def list_campaign_channels(campaign_id: UUID, organization_id: UUID,
                                user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select id,organization_id,campaign_id,channel_key,source_label,external_reference,spend_amount,created_at
                    from public.campaign_channels where organization_id=%s and campaign_id=%s order by created_at""",
                    [organization_id,campaign_id])
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/campaigns/{campaign_id}/channels", status_code=201)
async def create_campaign_channel(campaign_id: UUID, payload: CampaignChannelCreate,
                                  user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.campaign_channels
                    (organization_id,campaign_id,channel_key,source_label,external_reference,spend_amount)
                    select %s,c.id,%s,%s,%s,%s from public.recruitment_campaigns c
                    where c.id=%s and c.organization_id=%s
                    returning id,organization_id,campaign_id,channel_key,source_label,external_reference,spend_amount,created_at""",
                    [payload.organization_id,payload.channel_key,payload.source_label,payload.external_reference,
                     payload.spend_amount,campaign_id,payload.organization_id])
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Campaign not found")
                cursor.execute("""insert into public.campaign_events
                    (organization_id,campaign_id,actor_user_id,event_type,new_value)
                    values (%s,%s,%s,'updated',%s::jsonb)""",
                    [payload.organization_id,campaign_id,user_id,json.dumps({"channel_key":payload.channel_key})])
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Campaign channel already exists or the supplied values are invalid") from exc


@router.get("/referrals")
async def list_referrals(organization_id: UUID, campaign_id: UUID | None = None,
                         user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                sql = """select r.id,r.organization_id,r.campaign_id,r.channel_id,r.candidate_id,r.application_id,
                    r.referrer_user_id,r.referrer_name,r.status,r.notes,r.received_at,r.updated_at
                    from public.referrals r where r.organization_id=%s"""
                params: list[object] = [organization_id]
                if campaign_id:
                    sql += " and r.campaign_id=%s"; params.append(campaign_id)
                sql += " order by r.received_at desc limit 500"
                cursor.execute(sql, params)
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/referrals", status_code=201)
async def create_referral(payload: ReferralCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.referrals
                    (organization_id,campaign_id,channel_id,candidate_id,application_id,referrer_user_id,referrer_name,notes,created_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    returning id,organization_id,campaign_id,channel_id,candidate_id,application_id,referrer_user_id,referrer_name,status,notes,received_at,updated_at""",
                    [payload.organization_id,payload.campaign_id,payload.channel_id,payload.candidate_id,
                     payload.application_id,payload.referrer_user_id,payload.referrer_name,payload.notes,user_id])
                row = cursor.fetchone()
                if row["campaign_id"]:
                    if row["candidate_id"]:
                        cursor.execute("""insert into public.campaign_memberships
                            (organization_id,campaign_id,candidate_id,application_id,channel_id,attribution_type,created_by)
                            values (%s,%s,%s,%s,%s,'manual',%s)
                            on conflict (organization_id,campaign_id,candidate_id,attribution_type) do nothing""",
                            [payload.organization_id,row["campaign_id"],row["candidate_id"],row["application_id"],
                             row["channel_id"],user_id])
                    cursor.execute("""insert into public.campaign_events
                        (organization_id,campaign_id,candidate_id,application_id,actor_user_id,event_type,new_value)
                        values (%s,%s,%s,%s,%s,'referral_received',%s::jsonb)""",
                        [payload.organization_id,row["campaign_id"],row["candidate_id"],row["application_id"],user_id,
                         json.dumps({"referral_id":str(row["id"]),"status":"received"})])
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'referral_created','referral',%s,%s::jsonb)""",
                    [payload.organization_id,user_id,row["id"],json.dumps({"campaign_id":str(row["campaign_id"]) if row["campaign_id"] else None})])
                return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Referral could not be created; verify organisation-scoped candidate, application and campaign references") from exc


@router.patch("/referrals/{referral_id}/status")
async def update_referral_status(referral_id: UUID, payload: ReferralStatusUpdate,
                                 user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select id,status,campaign_id,candidate_id,application_id from public.referrals where id=%s and organization_id=%s for update",
                               [referral_id,payload.organization_id])
                previous = cursor.fetchone()
                if not previous:
                    raise HTTPException(status_code=404, detail="Referral not found")
                cursor.execute("update public.referrals set status=%s,updated_at=now() where id=%s and organization_id=%s returning id,status,updated_at",
                               [payload.status,referral_id,payload.organization_id])
                updated = cursor.fetchone()
                cursor.execute("""insert into public.audit_events
                    (organization_id,actor_user_id,action,entity_type,entity_id,metadata)
                    values (%s,%s,'referral_status_corrected','referral',%s,%s::jsonb)""",
                    [payload.organization_id,user_id,referral_id,json.dumps({"previous_status":previous["status"],"new_status":payload.status,"reason":payload.reason.strip()})])
                if previous["campaign_id"]:
                    cursor.execute("""insert into public.campaign_events
                        (organization_id,campaign_id,candidate_id,application_id,actor_user_id,event_type,previous_value,new_value,reason)
                        values (%s,%s,%s,%s,%s,'status_corrected',%s::jsonb,%s::jsonb,%s)""",
                        [payload.organization_id,previous["campaign_id"],previous["candidate_id"],previous["application_id"],user_id,
                         json.dumps({"status":previous["status"]}),json.dumps({"status":payload.status}),payload.reason.strip()])
                return updated
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
