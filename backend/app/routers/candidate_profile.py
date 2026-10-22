from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.candidate_profile import (
    CertificationBase,
    EducationBase,
    EmploymentBase,
    LanguageBase,
)

router = APIRouter(prefix="/api/candidates/{candidate_id}/profile", tags=["candidate-profile"])

# Table and model identifiers are fixed server-side; user input is never interpolated as SQL identifiers.
RECORD_TYPES = {
    "employment": ("candidate_employment_history", EmploymentBase, ("employer_name", "job_title", "location", "employment_type", "start_date", "end_date", "is_current", "description")),
    "education": ("candidate_education", EducationBase, ("institution_name", "qualification", "field_of_study", "start_date", "end_date", "grade", "description")),
    "certifications": ("candidate_certifications", CertificationBase, ("name", "issuing_organisation", "credential_id", "credential_url", "issued_on", "expires_on")),
    "languages": ("candidate_languages", LanguageBase, ("language", "proficiency")),
}


def _candidate_org(candidate_id: UUID) -> UUID:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.candidates where id = %s", [candidate_id])
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Candidate not found")
                return row["organization_id"]
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


def _execute(candidate_id: UUID, operation):
    organization_id = _candidate_org(candidate_id)
    table, model, fields = RECORD_TYPES[operation["kind"]]
    assert_org_member(operation["user_id"], organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if operation["action"] == "list":
                    cursor.execute(
                        f"select * from public.{table} where candidate_id = %s and organization_id = %s order by created_at desc",
                        [candidate_id, organization_id],
                    )
                    return cursor.fetchall()
                if operation["action"] == "create":
                    values = operation["payload"].model_dump(mode="json")
                    columns = list(values)
                    placeholders = ", ".join(["%s"] * len(columns))
                    cursor.execute(
                        f"insert into public.{table} (organization_id, candidate_id, {', '.join(columns)}) values (%s, %s, {placeholders}) returning *",
                        [organization_id, candidate_id, *[values[c] for c in columns]],
                    )
                    return cursor.fetchone()
                record_id = operation["record_id"]
                if operation["action"] == "update":
                    values = operation["payload"].model_dump(mode="json", exclude_unset=True)
                    if not values:
                        raise HTTPException(status_code=400, detail="No fields supplied")
                    assignments = ", ".join(f"{column} = %s" for column in values)
                    cursor.execute(
                        f"update public.{table} set {assignments}, updated_at = now() where id = %s and candidate_id = %s and organization_id = %s returning *",
                        [*[values[c] for c in values], record_id, candidate_id, organization_id],
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise HTTPException(status_code=404, detail="Profile record not found")
                    return row
                cursor.execute(
                    f"delete from public.{table} where id = %s and candidate_id = %s and organization_id = %s returning id",
                    [record_id, candidate_id, organization_id],
                )
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Profile record not found")
                return None
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


def _bind(kind: str, action: str, candidate_id: UUID, user_id: UUID, payload=None, record_id=None):
    return _execute(candidate_id, {"kind": kind, "action": action, "user_id": user_id, "payload": payload, "record_id": record_id})


def _register(kind: str, model):
    @router.get(f"/{kind}")
    def list_records(candidate_id: UUID, user_id: UUID = Depends(get_current_user_id)):
        return _bind(kind, "list", candidate_id, user_id)

    @router.post(f"/{kind}", status_code=201)
    def create_record(candidate_id: UUID, payload: model, user_id: UUID = Depends(get_current_user_id)):
        return _bind(kind, "create", candidate_id, user_id, payload=payload)

    @router.patch(f"/{kind}/{{record_id}}")
    def update_record(candidate_id: UUID, record_id: UUID, payload: model, user_id: UUID = Depends(get_current_user_id)):
        return _bind(kind, "update", candidate_id, user_id, payload=payload, record_id=record_id)

    @router.delete(f"/{kind}/{{record_id}}", status_code=204)
    def delete_record(candidate_id: UUID, record_id: UUID, user_id: UUID = Depends(get_current_user_id)):
        _bind(kind, "delete", candidate_id, user_id, record_id=record_id)
        return None


for _kind, (_table, _model, _fields) in RECORD_TYPES.items():
    _register(_kind, _model)
