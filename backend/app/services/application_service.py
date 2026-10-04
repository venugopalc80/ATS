from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.applications import ApplicationCreate, ApplicationUpdate


APPLICATION_COLUMNS = """
    id, organization_id, job_id, candidate_id, source, status,
    match_score, match_explanation, human_reviewed, human_reviewed_by,
    human_reviewed_at, created_at, updated_at
"""


class ApplicationService:
    async def list_applications(
        self,
        organization_id: UUID,
        status: str | None = None,
        job_id: UUID | None = None,
        candidate_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        query = f"""
            select {APPLICATION_COLUMNS}
            from public.applications
            where organization_id = %s
        """
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
                    f"""
                    insert into public.applications (
                        organization_id, job_id, candidate_id, source, status
                    )
                    values (%s, %s, %s, %s, %s)
                    returning {APPLICATION_COLUMNS}
                    """,
                    [
                        payload.organization_id,
                        payload.job_id,
                        payload.candidate_id,
                        payload.source,
                        payload.status,
                    ],
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Application was not created")
                return row

    async def get_application(self, application_id: UUID) -> dict[str, Any] | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {APPLICATION_COLUMNS} from public.applications where id = %s",
                    [application_id],
                )
                return cursor.fetchone()

    async def update_application(
        self, application_id: UUID, payload: ApplicationUpdate
    ) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_application(application_id)

        assignments = ", ".join(f"{column} = %s" for column in data)
        values = list(data.values()) + [application_id]

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.applications
                    set {assignments}, updated_at = now()
                    where id = %s
                    returning {APPLICATION_COLUMNS}
                    """,
                    values,
                )
                return cursor.fetchone()

    async def delete_application(self, application_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.applications where id = %s", [application_id])
                return cursor.rowcount > 0
