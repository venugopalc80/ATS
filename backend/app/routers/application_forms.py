from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(tags=["application forms"])
admin_router = APIRouter(prefix="/api/application-forms", tags=["application forms"])
public_router = APIRouter(prefix="/api/public/jobs", tags=["public application forms"])

FieldType = Literal["text", "textarea", "email", "phone", "number", "date", "select", "radio", "checkbox", "multi_select", "boolean"]


class QuestionIn(BaseModel):
    question_key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,79}$")
    label: str = Field(min_length=1, max_length=500)
    help_text: str | None = Field(default=None, max_length=2000)
    field_type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    validation: dict[str, Any] = Field(default_factory=dict)
    is_eligibility: bool = False
    position: int = Field(default=0, ge=0, le=10000)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question label cannot be blank")
        return value.strip()

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[str]):
        cleaned = [item.strip()[:200] for item in value if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Question options must be unique")
        return cleaned

    @field_validator("validation")
    @classmethod
    def validate_rules(cls, value: dict[str, Any]):
        for key in ("min", "max"):
            if key in value and (isinstance(value[key], bool) or not isinstance(value[key], (int, float)) or not math.isfinite(value[key])):
                raise ValueError("Numeric validation bounds must be finite numbers")
        if value.get("min") is not None and value.get("max") is not None and value["min"] > value["max"]:
            raise ValueError("Minimum validation bound cannot exceed maximum")
        return value


class FormCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    privacy_notice_text: str = Field(min_length=1, max_length=12000)
    privacy_notice_version: str = Field(default="1", min_length=1, max_length=80)
    questions: list[QuestionIn] = Field(default_factory=list, max_length=100)

    @field_validator("name", "privacy_notice_text")
    @classmethod
    def non_blank_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()


class FormVersionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    privacy_notice_text: str = Field(min_length=1, max_length=12000)
    privacy_notice_version: str = Field(default="1", min_length=1, max_length=80)
    questions: list[QuestionIn] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Form name cannot be blank")
        return value.strip() if value is not None else None

    @field_validator("privacy_notice_text")
    @classmethod
    def notice_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Privacy notice cannot be blank")
        return value.strip()


class AssignFormIn(BaseModel):
    organization_id: UUID
    form_version_id: UUID


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Application form service unavailable")


def assert_form_manager(user_id: UUID, organization_id: UUID) -> None:
    if get_org_role(user_id, organization_id) not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Recruiter or organisation admin access required")


def _insert_questions(cursor, organization_id: UUID, version_id: UUID, questions: list[QuestionIn]) -> None:
    keys = [q.question_key for q in questions]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Question keys must be unique within a form version")
    for question in questions:
        if question.field_type in {"select", "radio", "multi_select"} and not question.options:
            raise HTTPException(status_code=422, detail=f"Question '{question.question_key}' needs at least one option")
        cursor.execute(
            """insert into public.application_form_questions
               (organization_id, form_version_id, question_key, label, help_text, field_type,
                required, options, validation, is_eligibility, position)
               values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
            [organization_id, version_id, question.question_key, question.label, question.help_text,
             question.field_type, question.required, __import__("json").dumps(question.options),
             __import__("json").dumps(question.validation), question.is_eligibility, question.position],
        )


def _questions(cursor, version_id: UUID) -> list[dict[str, Any]]:
    cursor.execute(
        """select id, question_key, label, help_text, field_type, required, options,
                  validation, is_eligibility, position
             from public.application_form_questions
            where form_version_id=%s order by position, id""",
        [version_id],
    )
    return list(cursor.fetchall())


@admin_router.get("")
async def list_forms(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select t.id, t.organization_id, t.name, t.description, t.created_at, t.updated_at,
                              v.id as latest_version_id, v.version_number, v.status, v.published_at
                         from public.application_form_templates t
                         left join lateral (
                           select id, version_number, status, published_at
                             from public.application_form_versions
                            where template_id=t.id and organization_id=t.organization_id
                            order by version_number desc limit 1
                         ) v on true
                        where t.organization_id=%s order by t.updated_at desc""",
                    [organization_id],
                )
                return list(cursor.fetchall())
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.post("", status_code=201)
async def create_form(payload: FormCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_form_manager(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.application_form_templates
                       (organization_id, name, description, created_by)
                       values (%s,%s,%s,%s) returning id, organization_id, name, description, created_at, updated_at""",
                    [payload.organization_id, payload.name.strip(), payload.description, user_id],
                )
                template = cursor.fetchone()
                cursor.execute(
                    """insert into public.application_form_versions
                       (organization_id, template_id, version_number, status, privacy_notice_text,
                        privacy_notice_version, created_by)
                       values (%s,%s,1,'draft',%s,%s,%s) returning id, version_number, status, published_at""",
                    [payload.organization_id, template["id"], payload.privacy_notice_text.strip(),
                     payload.privacy_notice_version.strip(), user_id],
                )
                version = cursor.fetchone()
                _insert_questions(cursor, payload.organization_id, version["id"], payload.questions)
                return {**template, "version": version, "questions": _questions(cursor, version["id"])}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.get("/{template_id}")
async def get_form(template_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, name, description, created_at, updated_at
                         from public.application_form_templates where id=%s""",
                    [template_id],
                )
                template = cursor.fetchone()
                if template is None:
                    raise HTTPException(status_code=404, detail="Application form not found")
                assert_org_member(user_id, template["organization_id"])
                cursor.execute(
                    """select id, version_number, status, privacy_notice_text, privacy_notice_version,
                              created_at, published_at
                         from public.application_form_versions
                        where template_id=%s and organization_id=%s order by version_number desc""",
                    [template_id, template["organization_id"]],
                )
                versions = list(cursor.fetchall())
                for version in versions:
                    version["questions"] = _questions(cursor, version["id"])
                return {**template, "versions": versions}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.post("/{template_id}/versions", status_code=201)
async def create_version(template_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, name, description from public.application_form_templates where id=%s""",
                    [template_id],
                )
                template = cursor.fetchone()
                if template is None:
                    raise HTTPException(status_code=404, detail="Application form not found")
                assert_form_manager(user_id, template["organization_id"])
                cursor.execute(
                    """select id, version_number, privacy_notice_text, privacy_notice_version
                         from public.application_form_versions
                        where template_id=%s and organization_id=%s order by version_number desc limit 1""",
                    [template_id, template["organization_id"]],
                )
                previous = cursor.fetchone()
                next_number = int(previous["version_number"]) + 1
                cursor.execute(
                    """insert into public.application_form_versions
                       (organization_id, template_id, version_number, status, privacy_notice_text,
                        privacy_notice_version, created_by)
                       values (%s,%s,%s,'draft',%s,%s,%s) returning id, version_number, status""",
                    [template["organization_id"], template_id, next_number, previous["privacy_notice_text"],
                     previous["privacy_notice_version"], user_id],
                )
                version = cursor.fetchone()
                cursor.execute(
                    """insert into public.application_form_questions
                       (organization_id, form_version_id, question_key, label, help_text, field_type,
                        required, options, validation, is_eligibility, position)
                       select organization_id, %s, question_key, label, help_text, field_type,
                              required, options, validation, is_eligibility, position
                         from public.application_form_questions where form_version_id=%s""",
                    [version["id"], previous["id"]],
                )
                return {**template, "version": version, "questions": _questions(cursor, version["id"])}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.put("/versions/{version_id}")
async def update_version(version_id: UUID, payload: FormVersionUpdate, user_id: UUID = Depends(get_current_user_id)):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, template_id, status from public.application_form_versions where id=%s""",
                    [version_id],
                )
                version = cursor.fetchone()
                if version is None:
                    raise HTTPException(status_code=404, detail="Form version not found")
                assert_form_manager(user_id, version["organization_id"])
                if version["status"] != "draft":
                    raise HTTPException(status_code=409, detail="Published or archived form versions are immutable; create a new version")
                cursor.execute(
                    """update public.application_form_templates set name=coalesce(%s,name),
                              description=coalesce(%s,description), updated_at=now()
                        where id=%s and organization_id=%s""",
                    [payload.name.strip() if payload.name else None, payload.description,
                     version["template_id"], version["organization_id"]],
                )
                cursor.execute(
                    """update public.application_form_versions set privacy_notice_text=%s,
                              privacy_notice_version=%s where id=%s and organization_id=%s""",
                    [payload.privacy_notice_text.strip(), payload.privacy_notice_version.strip(),
                     version_id, version["organization_id"]],
                )
                cursor.execute("delete from public.application_form_questions where form_version_id=%s", [version_id])
                _insert_questions(cursor, version["organization_id"], version_id, payload.questions)
                return {"version_id": version_id, "status": "draft", "questions": _questions(cursor, version_id)}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.post("/versions/{version_id}/publish")
async def publish_version(version_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, organization_id, template_id, status, privacy_notice_text
                         from public.application_form_versions where id=%s""",
                    [version_id],
                )
                version = cursor.fetchone()
                if version is None:
                    raise HTTPException(status_code=404, detail="Form version not found")
                assert_org_admin(user_id, version["organization_id"])
                if version["status"] != "draft":
                    raise HTTPException(status_code=409, detail="Only draft versions can be published")
                if not version["privacy_notice_text"].strip():
                    raise HTTPException(status_code=422, detail="A privacy notice is required before publication")
                cursor.execute("select count(*) as count from public.application_form_questions where form_version_id=%s", [version_id])
                count = int(cursor.fetchone()["count"])
                if count == 0:
                    raise HTTPException(status_code=422, detail="Add at least one question before publishing")
                cursor.execute(
                    """update public.application_form_versions set status='published', published_at=%s
                        where id=%s and organization_id=%s returning id, version_number, status, published_at""",
                    [datetime.now(timezone.utc), version_id, version["organization_id"]],
                )
                return cursor.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@admin_router.put("/jobs/{job_id}/assignment")
async def assign_form(job_id: UUID, payload: AssignFormIn, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id from public.jobs where id=%s and organization_id=%s""",
                    [job_id, payload.organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Job not found")
                cursor.execute(
                    """select id from public.application_form_versions
                        where id=%s and organization_id=%s and status='published'""",
                    [payload.form_version_id, payload.organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=422, detail="Select a published form version")
                cursor.execute(
                    """insert into public.job_application_forms
                       (organization_id, job_id, form_version_id, created_by)
                       values (%s,%s,%s,%s)
                       on conflict (organization_id, job_id) do update
                         set form_version_id=excluded.form_version_id, updated_at=now()
                       returning id, organization_id, job_id, form_version_id, updated_at""",
                    [payload.organization_id, job_id, payload.form_version_id, user_id],
                )
                return cursor.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@public_router.get("/{job_id}/application-form")
async def get_public_application_form(job_id: UUID, organization_id: UUID):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select v.id as form_version_id, v.version_number, v.privacy_notice_text,
                              v.privacy_notice_version, t.name as form_name
                         from public.job_application_forms a
                         join public.application_form_versions v
                           on v.id=a.form_version_id and v.organization_id=a.organization_id
                         join public.application_form_templates t
                           on t.id=v.template_id and t.organization_id=v.organization_id
                         join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
                        where a.job_id=%s and a.organization_id=%s
                          and v.status='published' and j.status='open'""",
                    [job_id, organization_id],
                )
                version = cursor.fetchone()
                if version is None:
                    raise HTTPException(status_code=404, detail="No published application form is available for this job")
                version["questions"] = _questions(cursor, version["form_version_id"])
                # Public clients must not receive internal validation rules or recruiter-only metadata.
                for question in version["questions"]:
                    question.pop("validation", None)
                return version
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


