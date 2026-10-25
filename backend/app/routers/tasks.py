from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/tasks", tags=["recruiter tasks"])
TaskStatus = Literal["open", "completed", "cancelled"]
TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskType = Literal["task", "candidate_follow_up"]


class TaskCreate(BaseModel):
    organization_id: UUID
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType = "task"
    priority: TaskPriority = "normal"
    due_at: datetime | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    task_type: TaskType | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    assigned_to: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Task data is temporarily unavailable")


def _validate_related_records(organization_id: UUID, candidate_id: UUID | None, job_id: UUID | None) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if candidate_id is not None:
                    cursor.execute(
                        "select 1 from public.candidates where id=%s and organization_id=%s",
                        [candidate_id, organization_id],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Candidate must belong to this organization")
                if job_id is not None:
                    cursor.execute(
                        "select 1 from public.jobs where id=%s and organization_id=%s",
                        [job_id, organization_id],
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=422, detail="Vacancy must belong to this organization")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc



def _validate_assignee(organization_id: UUID, assigned_to: UUID | None) -> None:
    if assigned_to is None:
        return
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select 1 from public.organization_members where organization_id=%s and user_id=%s",
                    [organization_id, assigned_to],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=422, detail="Assignee must be a member of this organization")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc


def _task_dict(row: dict) -> dict:
    result = dict(row)
    for key in ("id", "organization_id", "candidate_id", "job_id", "assigned_to", "created_by"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    return result


@router.get("")
async def list_tasks(
    organization_id: UUID,
    status: TaskStatus | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    clauses = ["t.organization_id=%s"]
    params: list = [organization_id]
    if status:
        clauses.append("t.status=%s")
        params.append(status)
    if due_before:
        clauses.append("t.due_at <= %s")
        params.append(due_before)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select t.*, c.first_name as candidate_first_name, c.last_name as candidate_last_name,
                               j.title as job_title, p.full_name as assignee_name
                        from public.recruiter_tasks t
                        left join public.candidates c on c.id=t.candidate_id and c.organization_id=t.organization_id
                        left join public.jobs j on j.id=t.job_id and j.organization_id=t.organization_id
                        left join public.profiles p on p.id=t.assigned_to
                        where {' and '.join(clauses)}
                        order by case t.priority when 'urgent' then 0 when 'high' then 1 when 'normal' then 2 else 3 end,
                                 t.due_at asc nulls last, t.created_at desc limit 200""",
                    params,
                )
                return [_task_dict(row) for row in cursor.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc


@router.post("", status_code=201)
async def create_task(payload: TaskCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    _validate_related_records(payload.organization_id, payload.candidate_id, payload.job_id)
    _validate_assignee(payload.organization_id, payload.assigned_to)
    title = payload.title.strip()
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.recruiter_tasks
                       (organization_id,title,description,task_type,priority,due_at,candidate_id,job_id,assigned_to,created_by)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
                    [payload.organization_id, title, payload.description, payload.task_type, payload.priority,
                     payload.due_at, payload.candidate_id, payload.job_id, payload.assigned_to, user_id],
                )
                return _task_dict(cursor.fetchone())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc


@router.patch("/{task_id}")
async def update_task(task_id: UUID, payload: TaskUpdate, user_id: UUID = Depends(get_current_user_id)):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.recruiter_tasks where id=%s", [task_id])
                existing = cursor.fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Task not found")
                organization_id = existing["organization_id"]
                assert_org_member(user_id, organization_id)
                changes = payload.model_dump(exclude_unset=True)
                for required_field in ("title", "task_type", "status", "priority"):
                    if required_field in changes and changes[required_field] is None:
                        raise HTTPException(status_code=422, detail=f"{required_field} cannot be null")
                if "title" in changes and changes["title"] is not None:
                    changes["title"] = changes["title"].strip()
                _validate_related_records(organization_id, changes.get("candidate_id"), changes.get("job_id"))
                if "assigned_to" in changes:
                    _validate_assignee(organization_id, changes["assigned_to"])
                if not changes:
                    cursor.execute(
                        """select t.*, c.first_name as candidate_first_name, c.last_name as candidate_last_name,
                                  j.title as job_title, p.full_name as assignee_name
                           from public.recruiter_tasks t
                           left join public.candidates c on c.id=t.candidate_id and c.organization_id=t.organization_id
                           left join public.jobs j on j.id=t.job_id and j.organization_id=t.organization_id
                           left join public.profiles p on p.id=t.assigned_to where t.id=%s""", [task_id]
                    )
                    return _task_dict(cursor.fetchone())
                assignments = [f"{key}=%s" for key in changes]
                values = list(changes.values())
                if changes.get("status") == "completed":
                    assignments.append("completed_at=coalesce(completed_at,now())")
                    assignments.append("completed_by=%s")
                    values.append(user_id)
                elif changes.get("status") in ("open", "cancelled"):
                    assignments.append("completed_at=null")
                    assignments.append("completed_by=null")
                assignments.append("updated_at=now()")
                values.extend([task_id, organization_id])
                cursor.execute(
                    f"""update public.recruiter_tasks set {', '.join(assignments)}
                        where id=%s and organization_id=%s
                        returning *""",
                    values,
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Task not found")
                return _task_dict(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: UUID, user_id: UUID = Depends(get_current_user_id)) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.recruiter_tasks where id=%s", [task_id])
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Task not found")
                assert_org_member(user_id, row["organization_id"])
                cursor.execute(
                    "delete from public.recruiter_tasks where id=%s and organization_id=%s",
                    [task_id, row["organization_id"]],
                )
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _unavailable(exc) from exc
