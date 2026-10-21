from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import IntegrityError

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.tasks import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
_COLUMNS = "id,organization_id,title,description,task_type,status,priority,due_at,candidate_id,job_id,assigned_to,created_by,completed_at,completed_by,created_at,updated_at"


def _ensure_links(organization_id: UUID, candidate_id: UUID | None, job_id: UUID | None) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if candidate_id:
                    cursor.execute("select 1 from public.candidates where id=%s and organization_id=%s", [candidate_id, organization_id])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Candidate not found in this organization")
                if job_id:
                    cursor.execute("select 1 from public.jobs where id=%s and organization_id=%s", [job_id, organization_id])
                    if cursor.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Vacancy not found in this organization")
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Task references or status are invalid") from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


def _ensure_assignee(organization_id: UUID, assigned_to: UUID | None) -> None:
    if assigned_to is None:
        return
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1 from public.organization_members where organization_id=%s and user_id=%s", [organization_id, assigned_to])
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=422, detail="Assignee must be a member of this organization")
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    organization_id: UUID,
    status: str = Query(default="open", pattern="^(open|completed|cancelled|all)$"),
    task_type: str | None = Query(default=None, pattern="^(task|candidate_follow_up)$"),
    due_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    clauses = ["organization_id=%s"]
    params: list[object] = [organization_id]
    if status != "all":
        clauses.append("status=%s")
        params.append(status)
    if task_type:
        clauses.append("task_type=%s")
        params.append(task_type)
    if due_before:
        clauses.append("due_at is not null and due_at <= %s")
        params.append(due_before)
    params.append(limit)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {_COLUMNS} from public.recruiter_tasks where {' and '.join(clauses)} "
                    "order by case when status='open' and due_at < now() then 0 when status='open' then 1 else 2 end, "
                    "case priority when 'urgent' then 0 when 'high' then 1 when 'normal' then 2 else 3 end, due_at asc nulls last, created_at desc limit %s",
                    params,
                )
                return [TaskOut.model_validate(row) for row in cursor.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    _ensure_links(payload.organization_id, payload.candidate_id, payload.job_id)
    _ensure_assignee(payload.organization_id, payload.assigned_to)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.recruiter_tasks (organization_id,title,description,task_type,priority,due_at,candidate_id,job_id,assigned_to,created_by) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning " + _COLUMNS,
                    [payload.organization_id,payload.title,payload.description,payload.task_type,payload.priority,payload.due_at,payload.candidate_id,payload.job_id,payload.assigned_to,user_id],
                )
                return TaskOut.model_validate(cursor.fetchone())
    except IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Task references or status are invalid") from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: UUID, payload: TaskUpdate, user_id: UUID = Depends(get_current_user_id)):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="At least one field must be supplied")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id,candidate_id,job_id,task_type from public.recruiter_tasks where id=%s", [task_id])
                current = cursor.fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Task not found")
                organization_id = current["organization_id"]
                assert_org_member(user_id, organization_id)
                candidate_id = fields.get("candidate_id", current["candidate_id"])
                job_id = fields.get("job_id", current["job_id"])
                if current["task_type"] == "candidate_follow_up" and candidate_id is None:
                    raise HTTPException(status_code=422, detail="A candidate follow-up must remain linked to a candidate")
                _ensure_links(organization_id, candidate_id, job_id)
                if "assigned_to" in fields:
                    _ensure_assignee(organization_id, fields["assigned_to"])
                if fields.get("status") == "completed":
                    fields["completed_at"] = datetime.now(timezone.utc)
                    fields["completed_by"] = user_id
                elif fields.get("status") in {"open", "cancelled"}:
                    fields["completed_at"] = None
                    fields["completed_by"] = None
                fields["updated_at"] = datetime.now(timezone.utc)
                assignments = ", ".join(f"{key}=%s" for key in fields)
                cursor.execute(
                    "update public.recruiter_tasks set " + assignments + " where id=%s and organization_id=%s returning " + _COLUMNS,
                    list(fields.values()) + [task_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Task not found")
                return TaskOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc
