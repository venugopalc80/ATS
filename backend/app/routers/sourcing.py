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
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
            where.append("(base.first_name ilike %s escape '\\' or coalesce(base.last_name,'') ilike %s escape '\\' or coalesce(base.current_title,'') ilike %s escape '\\' or coalesce(base.city,'') ilike %s escape '\\')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term] * 4)
        if criteria.skills:
            where.append("base.skills && %s::text[]")
            params.append(criteria.skills)
        if criteria.location:
            where.append("(coalesce(base.city,'') ilike %s escape '\\' or coalesce(base.region,'') ilike %s escape '\\' or coalesce(base.country_code,'') ilike %s escape '\\')")
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
            where.append("(concat_ws(' ',c.first_name,c.last_name) ilike %s escape '\\' or coalesce(j.title,'') ilike %s escape '\\')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term, term])
        if criteria.status:
            where.append("base.status = %s"); params.append(criteria.status)
        if criteria.source:
            where.append("base.source = %s"); params.append(criteria.source)
        if criteria.recruiter_id:
            where.append("j.recruiter_id = %s"); params.append(criteria.recruiter_id)
        if criteria.location:
            where.append("(coalesce(j.location,'') ilike %s escape '\\' or coalesce(j.country_code,'') ilike %s escape '\\')")
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
            where.append("(base.title ilike %s escape '\\' or coalesce(base.location,'') ilike %s escape '\\')")
            term = "%" + _escape_like(criteria.q.strip()) + "%"
            params.extend([term, term])
        if criteria.status:
            where.append("base.status = %s"); params.append(criteria.status)
        if criteria.recruiter_id:
            where.append("base.recruiter_id = %s"); params.append(criteria.recruiter_id)
        if criteria.location:
            where.append("(coalesce(base.location,'') ilike %s escape '\\' or coalesce(base.country_code,'') ilike %s escape '\\')")
            term = "%" + _escape_like(criteria.location.strip()) + "%"
            params.extend([term, term])
        if criteria.skills:
            where.append("base.required_skills && %s::text[]"); params.append(criteria.skills)
    else:
        joins = " join public.candidates c on c.id=base.candidate_id and c.organization_id=base.organization_id "
        select = """select base.id, 'document' as record_type, base.candidate_id, base.document_type,
          base.original_filename, base.content_type, base.created_at,
          concat_ws(' ',c.first_name,c.last_name) as candidate_name"""
        source = "public.candidate_documents base"
        where.append("base.deleted_at is null")
        if criteria.q:
            where.append("(base.original_filename ilike %s escape '\\' or concat_ws(' ',c.first_name,c.last_name) ilike %s escape '\\')")
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


@router.get("/campaigns")
async def list_campaigns(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select c.id,c.organization_id,c.name,c.description,c.status,c.target_job_id,
                    c.owner_user_id,c.starts_at,c.ends_at,c.budget_amount,c.budget_currency,c.attribution_window_days,
                    c.created_at,c.updated_at,count(distinct cm.candidate_id) as attributed_candidates,
                    count(distinct r.id) as referrals
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
