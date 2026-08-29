from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.jobs import JobCreate


class JobService:
    """Persistence boundary for job requisitions."""

    async def list_jobs(
        self, organization_id: UUID, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = """
            select id, organization_id, client_id, job_code, title, description,
                   location, country_code, employment_type, work_mode,
                   salary_min, salary_max, salary_currency, experience_min,
                   experience_max, work_authorization, required_skills,
                   preferred_skills, status, recruiter_id, hiring_manager_id,
                   created_by, created_at, updated_at
            from public.jobs
            where organization_id = %s
        """
        params: list[Any] = [organization_id]

        if status:
            query += " and status = %s"
            params.append(status)

        query += " order by created_at desc"

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_job(self, payload: JobCreate) -> dict[str, Any]:
        data = payload.model_dump(mode="python")
        columns = list(data.keys())
        values = [data[column] for column in columns]
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(columns)

        query = f"""
            insert into public.jobs ({column_sql})
            values ({placeholders})
            returning id, organization_id, client_id, job_code, title,
                      description, location, country_code, employment_type,
                      work_mode, salary_min, salary_max, salary_currency,
                      experience_min, experience_max, work_authorization,
                      required_skills, preferred_skills, status, recruiter_id,
                      hiring_manager_id, created_by, created_at, updated_at
        """

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Job was not created")
                return row

    async def get_job(self, job_id: UUID) -> dict[str, Any] | None:
        query = """
            select id, organization_id, client_id, job_code, title, description,
                   location, country_code, employment_type, work_mode,
                   salary_min, salary_max, salary_currency, experience_min,
                   experience_max, work_authorization, required_skills,
                   preferred_skills, status, recruiter_id, hiring_manager_id,
                   created_by, created_at, updated_at
            from public.jobs
            where id = %s
        """

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, [job_id])
                return cursor.fetchone()
