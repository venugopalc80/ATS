from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/public/jobs", tags=["public careers"])

PUBLIC_COLUMNS = """
    id, title, description, location, country_code, employment_type, work_mode,
    salary_min, salary_max, salary_currency, required_skills, created_at, updated_at
"""


@router.get("")
async def list_public_jobs(organization_id: UUID = Query(...)):
    """Public careers listing. Only open jobs are exposed; private recruiting fields are omitted."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select {PUBLIC_COLUMNS}
                        from public.jobs
                        where organization_id = %s and status = 'open'
                        order by updated_at desc""",
                    [organization_id],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Careers service unavailable") from exc


@router.get("/{job_id}")
async def get_public_job(job_id: UUID, organization_id: UUID = Query(...)):
    """Return a single open job only when it belongs to the requested organisation."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select {PUBLIC_COLUMNS}
                        from public.jobs
                        where id = %s and organization_id = %s and status = 'open'""",
                    [job_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Job not found")
                return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Careers service unavailable") from exc
