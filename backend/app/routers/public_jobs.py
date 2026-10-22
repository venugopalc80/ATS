from datetime import date, datetime, timezone
import math
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/public/jobs", tags=["public careers"])

PUBLIC_COLUMNS = """
    id, title, description, location, country_code, employment_type, work_mode,
    salary_min, salary_max, salary_currency, required_skills, created_at, updated_at
"""


class PublicApplicationIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(min_length=5, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    # Legacy application form: consent remains required by the old route.
    # Versioned forms instead record notice acknowledgement separately from optional marketing.
    consent: bool = False
    source: str = Field(default="careers_page", max_length=100)
    form_version_id: UUID | None = None
    answers: dict[str, Any] = Field(default_factory=dict, max_length=100)
    privacy_notice_acknowledged: bool = False
    marketing_opt_in: bool = False
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1] or any(ch.isspace() for ch in value):
            raise ValueError("Enter a valid email address")
        return value


def _validate_answer(question: dict[str, Any], value: Any) -> bool:
    field_type = question["field_type"]
    if value is None or value == "" or value == [] or (isinstance(value, str) and not value.strip()):
        return not question["required"]
    if field_type in {"text", "textarea", "email", "phone", "date"}:
        if not isinstance(value, str):
            return False
        if field_type == "email":
            return "@" in value and "." in value.rsplit("@", 1)[-1] and not any(ch.isspace() for ch in value)
        if field_type == "date":
            try:
                date.fromisoformat(value)
                return True
            except ValueError:
                return False
        return len(value) <= 12000
    if field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            return False
        rules = question.get("validation") or {}
        return (rules.get("min") is None or value >= rules["min"]) and (rules.get("max") is None or value <= rules["max"])
    if field_type in {"boolean", "checkbox"}:
        return isinstance(value, bool)
    if field_type in {"select", "radio"}:
        return isinstance(value, str) and value in (question.get("options") or [])
    if field_type == "multi_select":
        return isinstance(value, list) and all(isinstance(item, str) and item in (question.get("options") or []) for item in value)
    return False


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
    """Submit an application; versioned forms validate and persist their exact question set and answers."""
    version_questions: list[dict[str, Any]] = []
    notice_version: str | None = None
    if payload.form_version_id is None:
        if not payload.consent:
            raise HTTPException(status_code=422, detail="Please confirm the application processing notice")
    else:
        if not payload.privacy_notice_acknowledged:
            raise HTTPException(status_code=422, detail="Please acknowledge the applicant privacy notice")
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select v.id, v.privacy_notice_version
                             from public.job_application_forms a
                             join public.application_form_versions v
                               on v.id=a.form_version_id and v.organization_id=a.organization_id
                            where a.job_id=%s and a.organization_id=%s and a.form_version_id=%s
                              and v.status='published'""",
                        [job_id, organization_id, payload.form_version_id],
                    )
                    version = cursor.fetchone()
                    if version is None:
                        raise HTTPException(status_code=422, detail="This application form is no longer available")
                    notice_version = version["privacy_notice_version"]
                    cursor.execute(
                        """select id, question_key, field_type, required, options, validation
                             from public.application_form_questions
                            where form_version_id=%s and organization_id=%s order by position, id""",
                        [payload.form_version_id, organization_id],
                    )
                    version_questions = list(cursor.fetchall())
            expected_keys = {q["question_key"] for q in version_questions}
            if set(payload.answers.keys()) - expected_keys:
                raise HTTPException(status_code=422, detail="The form contains answers to unknown questions")
            for question in version_questions:
                answer = payload.answers.get(question["question_key"])
                if not _validate_answer(question, answer):
                    raise HTTPException(status_code=422, detail=f"Please provide a valid answer for: {question['question_key']}")
        except HTTPException:
            raise
        except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
            raise HTTPException(status_code=503, detail="Application form service unavailable") from exc

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

                if payload.idempotency_key and payload.form_version_id is not None:
                    cursor.execute("select pg_advisory_xact_lock(hashtext(%s), hashtext(%s))", [str(organization_id), payload.idempotency_key])
                    cursor.execute(
                        """select e.application_id from public.application_submission_events e
                            join public.applications a on a.id=e.application_id and a.organization_id=e.organization_id
                            where e.organization_id=%s and e.idempotency_key=%s and a.job_id=%s limit 1""",
                        [organization_id, payload.idempotency_key, job_id],
                    )
                    previous_submission = cursor.fetchone()
                    if previous_submission:
                        return {"success": True, "application_id": previous_submission["application_id"],
                                "message": "Your application has already been received."}

                cursor.execute(
                    "select id from public.candidates where organization_id=%s and lower(email)=lower(%s) order by created_at desc limit 1",
                    [organization_id, email],
                )
                existing = cursor.fetchone()
                if existing:
                    candidate_id = existing["id"]
                    if payload.form_version_id is None:
                        cursor.execute(
                            """update public.candidates
                               set consent_recorded_at=%s, consent_purpose=%s, updated_at=now()
                               where id=%s and organization_id=%s""",
                            [now, f"Application for job {job_id}", candidate_id, organization_id],
                        )
                else:
                    if payload.form_version_id is None:
                        cursor.execute(
                            """insert into public.candidates
                               (organization_id, first_name, last_name, email, phone, status,
                                consent_recorded_at, consent_purpose)
                               values (%s, %s, %s, %s, %s, 'active', %s, %s)
                               returning id""",
                            [organization_id, payload.first_name.strip(), payload.last_name.strip() or None,
                             email, payload.phone, now, f"Application for job {job_id}"],
                        )
                    else:
                        cursor.execute(
                            """insert into public.candidates
                               (organization_id, first_name, last_name, email, phone, status)
                               values (%s, %s, %s, %s, %s, 'active') returning id""",
                            [organization_id, payload.first_name.strip(), payload.last_name.strip() or None,
                             email, payload.phone],
                        )
                    candidate_id = cursor.fetchone()["id"]

                cursor.execute(
                    """select id from public.applications
                       where organization_id=%s and job_id=%s and candidate_id=%s
                         and status not in ('rejected', 'withdrawn') limit 1""",
                    [organization_id, job_id, candidate_id],
                )
                existing_application = cursor.fetchone()
                if existing_application:
                    # Do not silently create a second application. Explicit repeat applications need a separate reviewed workflow.
                    raise HTTPException(status_code=409, detail="An application already exists for this job and email address")

                cursor.execute(
                    """insert into public.applications
                       (organization_id, job_id, candidate_id, source, status)
                       values (%s, %s, %s, %s, 'new') returning id""",
                    [organization_id, job_id, candidate_id, source],
                )
                application_id = cursor.fetchone()["id"]

                if payload.form_version_id is not None:
                    import json
                    for question in version_questions:
                        if question["question_key"] in payload.answers:
                            cursor.execute(
                                """insert into public.application_answers
                                   (organization_id, application_id, form_version_id, question_id, answer)
                                   values (%s,%s,%s,%s,%s::jsonb)""",
                                [organization_id, application_id, payload.form_version_id, question["id"],
                                 json.dumps(payload.answers[question["question_key"]])],
                            )
                    cursor.execute(
                        """insert into public.application_submission_events
                           (organization_id, application_id, form_version_id, event_type,
                            privacy_notice_version, privacy_notice_acknowledged, marketing_opt_in,
                            idempotency_key, metadata)
                           values (%s,%s,%s,'submitted',%s,true,%s,%s,%s::jsonb)""",
                        [organization_id, application_id, payload.form_version_id, notice_version,
                         payload.marketing_opt_in, payload.idempotency_key,
                         json.dumps({"source": source, "question_count": len(version_questions)})],
                    )
                return {"success": True, "application_id": application_id, "message": "Your application has been received."}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Application service unavailable") from exc
