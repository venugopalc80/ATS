from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/public/jobs", tags=["public careers"])

PUBLIC_COLUMNS = """
    j.id, j.organization_id, j.client_id, j.title, j.description, j.location,
    j.country_code, j.employment_type, j.work_mode, j.salary_min, j.salary_max,
    j.salary_currency, j.required_skills, j.created_at, j.updated_at,
    c.name AS hiring_organization_name, c.website AS hiring_organization_website
"""


class PublicApplicationIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(min_length=5, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    consent: bool
    source: str = Field(default="careers_page", max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1] or any(ch.isspace() for ch in value):
            raise ValueError("Enter a valid email address")
        return value


def _public_job_filter() -> str:
    # Jobs must be explicitly selected for either the public careers page or Google.
    return """
        j.status = 'open'
        and exists (
            select 1
            from public.job_distribution_channels d
            where d.job_id = j.id
              and d.organization_id = j.organization_id
              and d.selected = true
              and d.channel_id in ('careers', 'google')
        )
    """


@router.get("")
async def list_public_jobs():
    """List only open jobs explicitly selected for public careers or Google discovery."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select {PUBLIC_COLUMNS}
                        from public.jobs j
                        left join public.clients c
                          on c.id = j.client_id and c.organization_id = j.organization_id
                        where {_public_job_filter()}
                        order by j.updated_at desc
                        limit 5000"""
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Careers service unavailable") from exc


@router.get("/{job_id}")
async def get_public_job(job_id: UUID):
    """Return a public job by globally unique ID, only if published and still open."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select {PUBLIC_COLUMNS}
                        from public.jobs j
                        left join public.clients c
                          on c.id = j.client_id and c.organization_id = j.organization_id
                        where j.id = %s and {_public_job_filter()}""",
                    [job_id],
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
async def apply_for_public_job(job_id: UUID, payload: PublicApplicationIn):
    """Create an application for a published job using its server-resolved tenant."""
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Consent is required to submit an application")
    email = str(payload.email).strip().lower()
    source = payload.source.strip()[:100] or "careers_page"
    now = datetime.now(timezone.utc)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""select j.organization_id
                        from public.jobs j
                        where j.id = %s and {_public_job_filter()}""",
                    [job_id],
                )
                job = cursor.fetchone()
                if job is None:
                    raise HTTPException(status_code=404, detail="Job not found or no longer accepting applications")
                organization_id = job["organization_id"]

                cursor.execute(
                    """select id from public.candidates
                       where organization_id=%s and lower(email)=lower(%s)
                       order by created_at desc limit 1""",
                    [organization_id, email],
                )
                existing = cursor.fetchone()
                if existing:
                    candidate_id = existing["id"]
                    cursor.execute(
                        """update public.candidates
                           set consent_recorded_at=%s, consent_purpose=%s, updated_at=now()
                           where id=%s and organization_id=%s""",
                        [now, f"Application for job {job_id}", candidate_id, organization_id],
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
