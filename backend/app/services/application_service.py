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
STAGE_HISTORY_COLUMNS = "id, organization_id, application_id, previous_stage, new_stage, actor_user_id, reason, created_at"


def _load_stage_config(cursor, organization_id: UUID) -> dict[str, dict[str, Any]]:
    cursor.execute(
        "select stage_key, enabled, allowed_next_stages from public.application_stage_config where organization_id=%s",
        [organization_id],
    )
    rows = cursor.fetchall()
    return {
        row["stage_key"]: {
            "enabled": bool(row["enabled"]),
            "allowed_next_stages": list(row["allowed_next_stages"] or []),
        }
        for row in rows
    }


def _validate_configured_transition(
    stage_config: dict[str, dict[str, Any]], current_status: str, target_status: str
) -> None:
    current = stage_config.get(current_status)
    target = stage_config.get(target_status)
    if current is None or target is None:
        raise ValueError("Application stage configuration is missing for this organisation")
    if not target["enabled"]:
        raise ValueError("Target application stage is disabled")
    if target_status not in current["allowed_next_stages"]:
        raise ValueError("Invalid application stage transition")


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
                    "select exists(select 1 from public.jobs where id=%s and organization_id=%s) as job_ok, exists(select 1 from public.candidates where id=%s and organization_id=%s) as candidate_ok",
                    [payload.job_id, payload.organization_id, payload.candidate_id, payload.organization_id],
                )
                links = cursor.fetchone()
                if not links["job_ok"] or not links["candidate_ok"]:
                    raise ValueError("Job and candidate must belong to the same organization")
                cursor.execute(
                    "insert into public.applications (organization_id, job_id, candidate_id, source, status) values (%s, %s, %s, %s, %s) returning " + APPLICATION_COLUMNS,
                    [payload.organization_id, payload.job_id, payload.candidate_id, payload.source, payload.status],
                )
                return cursor.fetchone()

    async def get_application(self, application_id: UUID) -> dict[str, Any] | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select " + APPLICATION_COLUMNS + " from public.applications where id=%s", [application_id])
                return cursor.fetchone()

    async def update_application(self, application_id: UUID, payload: ApplicationUpdate, actor_user_id: UUID) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_application(application_id)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status, organization_id from public.applications where id=%s for update", [application_id])
                existing = cursor.fetchone()
                if existing is None:
                    return None
                if "status" in data and data["status"] != existing["status"]:
                    stage_config = _load_stage_config(cursor, existing["organization_id"])
                    _validate_configured_transition(stage_config, existing["status"], data["status"])
                cursor.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                assignments = ", ".join(f"{column} = %s" for column in data)
                cursor.execute("update public.applications set " + assignments + ", updated_at=now() where id=%s returning " + APPLICATION_COLUMNS, list(data.values()) + [application_id])
                return cursor.fetchone()

    async def transition_application(
        self,
        application_id: UUID,
        status: str,
        actor_user_id: UUID,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Apply a permitted stage transition atomically; the DB trigger records its history."""
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select status, organization_id from public.applications where id=%s for update",
                    [application_id],
                )
                existing = cursor.fetchone()
                if existing is None:
                    return None
                current_status = existing["status"]
                if status == current_status:
                    cursor.execute(
                        "select " + APPLICATION_COLUMNS + " from public.applications where id=%s",
                        [application_id],
                    )
                    return cursor.fetchone()
                stage_config = _load_stage_config(cursor, existing["organization_id"])
                _validate_configured_transition(stage_config, current_status, status)
                cursor.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                cursor.execute("select set_config('app.transition_reason', %s, true)", [reason or ""])
                cursor.execute(
                    "update public.applications set status=%s, updated_at=now() where id=%s returning " + APPLICATION_COLUMNS,
                    [status, application_id],
                )
                return cursor.fetchone()

    async def list_stage_history(self, organization_id: UUID, application_id: UUID) -> list[dict[str, Any]]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select " + STAGE_HISTORY_COLUMNS + " from public.application_stage_history "
                    "where organization_id=%s and application_id=%s order by created_at desc, id desc",
                    [organization_id, application_id],
                )
                return list(cursor.fetchall())

    async def delete_application(self, application_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.applications where id=%s", [application_id])
                return cursor.rowcount > 0
