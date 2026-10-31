from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.candidates import CandidateBase, CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
service = CandidateService()


class BulkCandidateImportRequest(BaseModel):
    organization_id: UUID
    candidates: list[CandidateBase] = Field(min_length=1, max_length=500)


@router.post("/bulk-import")
async def bulk_import_candidates(
    payload: BulkCandidateImportRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    try:
        result = await service.bulk_create_candidates(
            payload.organization_id,
            [candidate.model_dump(mode="python", exclude_unset=False) for candidate in payload.candidates],
        )
        return {
            "imported": len(result["candidates"]),
            "duplicates": len(result["duplicate_rows"]),
            "duplicate_rows": result["duplicate_rows"],
            "candidates": [CandidateOut.model_validate(row).model_dump(mode="json") for row in result["candidates"]],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc




class CandidateEducationInput(BaseModel):
    institution: str | None = Field(default=None, max_length=240)
    qualification: str | None = Field(default=None, max_length=180)
    field_of_study: str | None = Field(default=None, max_length=180)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    raw_text: str = Field(min_length=1, max_length=500)


def _education_candidate_org(candidate_id: UUID, user_id: UUID) -> UUID:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.candidates where id=%s", [candidate_id])
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Candidate not found")
                organization_id = UUID(str(row["organization_id"]))
        assert_org_member(user_id, organization_id)
        return organization_id
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{candidate_id}/education")
async def list_candidate_education(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    organization_id = _education_candidate_org(candidate_id, user_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id, institution, qualification, field_of_study, start_year,
                              graduation_year, raw_text, created_at, updated_at
                       from public.candidate_education
                       where candidate_id=%s and organization_id=%s
                       order by graduation_year desc nulls last, created_at""",
                    [candidate_id, organization_id],
                )
                return cursor.fetchall()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.put("/{candidate_id}/education")
async def replace_candidate_education(
    candidate_id: UUID,
    records: list[CandidateEducationInput] = Body(..., max_length=30),
    user_id: UUID = Depends(get_current_user_id),
):
    organization_id = _education_candidate_org(candidate_id, user_id)
    for record in records:
        if record.start_year and record.graduation_year and record.start_year > record.graduation_year:
            raise HTTPException(status_code=422, detail="Start year cannot be after graduation year")
        if not record.raw_text.strip():
            raise HTTPException(status_code=422, detail="Education source text cannot be empty")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.candidate_education where candidate_id=%s and organization_id=%s",
                    [candidate_id, organization_id],
                )
                saved = []
                for record in records:
                    cursor.execute(
                        """insert into public.candidate_education
                           (organization_id, candidate_id, institution, qualification, field_of_study,
                            start_year, graduation_year, raw_text, updated_at)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,now())
                           returning id, institution, qualification, field_of_study, start_year,
                                     graduation_year, raw_text, created_at, updated_at""",
                        [organization_id, candidate_id, record.institution, record.qualification,
                         record.field_of_study, record.start_year, record.graduation_year,
                         record.raw_text.strip()],
                    )
                    saved.append(cursor.fetchone())
                return saved
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    organization_id: UUID,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    user_id: UUID = Depends(get_current_user_id),
) -> list[CandidateOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_candidates(organization_id, status, search)
        return [CandidateOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=CandidateOut, status_code=201)
async def create_candidate(
    payload: CandidateCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    assert_org_member(user_id, payload.organization_id)
    try:
        row = await service.create_candidate(payload)
        return CandidateOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    try:
        row = await service.get_candidate(candidate_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    assert_org_member(user_id, row["organization_id"])
    return CandidateOut.model_validate(row)


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    try:
        existing = await service.get_candidate(candidate_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_candidate(candidate_id, payload)
        return CandidateOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        existing = await service.get_candidate(candidate_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        assert_org_admin(user_id, existing["organization_id"])
        deleted = await service.delete_candidate(candidate_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")
