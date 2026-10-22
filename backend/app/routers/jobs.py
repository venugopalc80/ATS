from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.jobs import JobCreate, JobOut, JobUpdate
from app.services.google_indexing import notify_google_indexing
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
service = JobService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[JobOut])
async def list_jobs(
    organization_id: UUID,
    status: str | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
) -> list[JobOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_jobs(organization_id, status)
        return [JobOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_job(payload)
        if row.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    try:
        row = await service.get_job(job_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    assert_org_member(user_id, row["organization_id"])
    return JobOut.model_validate(row)


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: UUID,
    payload: JobUpdate,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> JobOut:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        role = get_org_role(user_id, existing["organization_id"])
        changes = payload.model_dump(exclude_unset=True)
        if ("recruiter_id" in changes or "hiring_manager_id" in changes) and role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Only organisation owners or admins can reassign vacancy ownership")
        if "status" in changes and changes["status"] != existing.get("status"):
            allowed = {"draft": {"open", "cancelled"}, "open": {"on_hold", "closed", "filled"}, "on_hold": {"open", "closed", "cancelled"}, "closed": {"open"}, "filled": set(), "cancelled": set()}
            if changes["status"] not in allowed.get(existing.get("status"), set()):
                raise HTTPException(status_code=409, detail="Invalid vacancy status transition")
            if role not in {"owner", "admin", "recruiter"}:
                raise HTTPException(status_code=403, detail="You cannot change vacancy status")
        row = await service.update_job(job_id, payload)
        if row is not None and changes:
            from psycopg.types.json import Jsonb
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata) values (%s,%s,%s,'job',%s,%s)",
                        [existing["organization_id"], user_id, "job.updated", job_id, Jsonb({"changed_fields": list(changes), "previous_status": existing.get("status"), "status": row.get("status")})],
                    )
        if row is not None:
            if row.get("status") == "open":
                background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_UPDATED")
            elif existing.get("status") == "open":
                background_tasks.add_task(notify_google_indexing, str(row["id"]), "URL_DELETED")
        return JobOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        existing = await service.get_job(job_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_org_member(user_id, existing["organization_id"])
        role = get_org_role(user_id, existing["organization_id"])
        if role not in {"owner", "admin", "recruiter"}:
            raise HTTPException(status_code=403, detail="You cannot close this vacancy")
        deleted = await service.delete_job(job_id)
        if deleted and existing.get("status") not in {"closed", "filled", "cancelled"}:
            from psycopg.types.json import Jsonb
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata) values (%s,%s,'job.closed','job',%s,%s)",
                        [existing["organization_id"], user_id, job_id, Jsonb({"previous_status": existing.get("status"), "status": "closed"})],
                    )
        if deleted and existing.get("status") == "open":
            background_tasks.add_task(notify_google_indexing, str(job_id), "URL_DELETED")
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
