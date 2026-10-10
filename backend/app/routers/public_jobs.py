from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/public/jobs", tags=["public careers"])

PUBLIC_COLUMNS = """
    id, title, description, location, country_code, employment_type, work_mode,
    salary_min, salary_max, salary_currency, required_skills, created_at, updated_at
"""


class PublicApplicationIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    consent: bool
    source: str = Field(default="careers_page", max_length=100)


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


@router.post("/{job_id}/applications", status_code=201)
async def apply_for_public_job(job_id: UUID, payload: PublicApplicationIn, organization_id: UUID = Query(...)):
    """Create a candidate and application from a public careers form."""
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Consent is required to submit an application")
    email = str(payload.email).strip().lower()
    source = payload.source.strip()[:100] or "careers_page"
    now = datetime.now(timezone.utc)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.jobs where id=%s and organization_id=%s and status='open'",
                    [job_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Job not found or no longer accepting applications")

                cursor.execute(
                    "select id from public.candidates where organization_id=%s and lower(email)=lower(%s) order by created_at desc limit 1",
                    [organization_id, email],
                )
                existing = cursor.fetchone()
                if existing:
                    candidate_id = existing["id"]
                    cursor.execute(
                        """update public.candidates
                           set consent_recorded_at=%s, consent_purpose=%s, updated_at=now()
                           where id=%s""",
                        [now, f"Application for job {job_id}", candidate_id],
                    )
                else:
                    cursor.execute(
                        """insert into public.candidates
                           (organization_id, first_name, last_name, email, phone, status,
                            consent_recorded_at, consent_purpose)
                           values (%s, %s, %s, %s, %s, 'active', %s, %s)
                           returning id""",
                        [organization_id, payload.first_name.strip(), payload.last_name.strip() or None,
                         email, payload.phone, now, f"Application for job {job_id}"],
                    )
                    candidate_id = cursor.fetchone()["id"]

                cursor.execute(
                    """select id from public.applications
                       where organization_id=%s and job_id=%s and candidate_id=%s
                         and status not in ('rejected', 'withdrawn')
                       limit 1""",
                    [organization_id, job_id, candidate_id],
                )
                if cursor.fetchone():
                    raise HTTPException(status_code=409, detail="An active application already exists for this job and email address")

                cursor.execute(
                    """insert into public.applications
                       (organization_id, job_id, candidate_id, source, status)
                       values (%s, %s, %s, %s, 'new') returning id""",
                    [organization_id, job_id, candidate_id, source],
                )
                application_id = cursor.fetchone()["id"]
                return {"success": True, "application_id": application_id, "message": "Your application has been received."}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Application service unavailable") from exc
