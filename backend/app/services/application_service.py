from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.applications import ApplicationCreate, ApplicationUpdate

ALLOWED_APPLICATION_TRANSITIONS = {
    "new": {"screening", "rejected", "withdrawn"},
    "screening": {"submitted", "rejected", "withdrawn"},
    "submitted": {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(), "rejected": set(), "withdrawn": set(),
}
APPLICATION_COLUMNS = "id, organization_id, job_id, candidate_id, source, status, match_score, match_explanation, human_reviewed, human_reviewed_by, human_reviewed_at, created_at, updated_at"


class ApplicationService:
    async def list_applications(self, organization_id: UUID, status: str | None = None, job_id: UUID | None = None, candidate_id: UUID | None = None) -> list[dict[str, Any]]:
        query = "select " + APPLICATION_COLUMNS + " from public.applications where organization_id = %s"
        params: list[Any] = [organization_id]
        if status:
            query += " and status = %s"
            params.append(status)
        if job_id:
            query += " and job_id = %s"
            params.append(job_id)
        if candidate_id:
            query += " and candidate_id = %s"
            params.append(candidate_id)
        query += " order by created_at desc"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_application(self, payload: ApplicationCreate) -> dict[str, Any]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                      (select status from public.jobs where id = %s and organization_id = %s) as job_status,
                      exists(
                        select 1 from public.candidates
                        where id = %s and organization_id = %s
                      ) as candidate_ok
                    """,
                    [payload.job_id, payload.organization_id, payload.candidate_id, payload.organization_id],
                )
                links = cursor.fetchone()
                if links["job_status"] != "open":
                    raise ValueError("Applications can only be added to open jobs")
                if not links["candidate_ok"]:
                    raise ValueError("Job and candidate must belong to the same organization")

                # Serialise concurrent requests for the same tenant/job/candidate tuple.
                # The transaction-scoped lock is released automatically on commit/rollback.
                lock_key = f"{payload.organization_id}:{payload.job_id}:{payload.candidate_id}"
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", [lock_key])
                cursor.execute(
                    """
                    select exists(
                      select 1 from public.applications
                      where organization_id = %s and job_id = %s and candidate_id = %s
                    ) as duplicate_application
                    """,
                    [payload.organization_id, payload.job_id, payload.candidate_id],
                )
                if cursor.fetchone()["duplicate_application"]:
                    raise ValueError("This candidate already has an application for that job")
                cursor.execute(
                    "insert into public.applications (organization_id, job_id, candidate_id, source, status) values (%s, %s, %s, %s, 'new') on conflict (job_id, candidate_id) do nothing returning " + APPLICATION_COLUMNS,
                    [payload.organization_id, payload.job_id, payload.candidate_id, payload.source],
                )
                created = cursor.fetchone()
                if created is None:
                    # Another creation path may have won the unique-key race without
                    # using the advisory lock. Convert it into a stable duplicate response.
                    raise ValueError("This candidate already has an application for that job")
                return created

    async def get_application(self, application_id: UUID) -> dict[str, Any] | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select " + APPLICATION_COLUMNS + " from public.applications where id=%s", [application_id])
                return cursor.fetchone()

    async def update_application(self, application_id: UUID, payload: ApplicationUpdate, actor_user_id: UUID) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_application(application_id)
        if "human_reviewed" in data:
            if data["human_reviewed"]:
                data["human_reviewed_by"] = actor_user_id
                data["human_reviewed_at"] = "now()"
            else:
                data["human_reviewed_by"] = None
                data["human_reviewed_at"] = None
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status from public.applications where id=%s for update", [application_id])
                existing = cursor.fetchone()
                if existing is None:
                    return None
                if "status" in data and data["status"] != existing["status"] and data["status"] not in ALLOWED_APPLICATION_TRANSITIONS.get(existing["status"], set()):
                    raise ValueError("Invalid application stage transition")
                cursor.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                assignments = []
                values = []
                for column, value in data.items():
                    if column == "human_reviewed_at" and value == "now()":
                        assignments.append("human_reviewed_at = now()")
                    else:
                        assignments.append(f"{column} = %s")
                        values.append(value)
                cursor.execute("update public.applications set " + ", ".join(assignments) + ", updated_at=now() where id=%s returning " + APPLICATION_COLUMNS, values + [application_id])
                return cursor.fetchone()

    async def delete_application(self, application_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.applications where id=%s", [application_id])
                return cursor.rowcount > 0
