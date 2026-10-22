from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
service = CandidateService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    response: Response,
    organization_id: UUID,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    country_code: str | None = Query(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$"),
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort_by: str = Query(default="name", pattern="^(name|title|location|status)$"),
    sort_direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    user_id: UUID = Depends(get_current_user_id),
) -> list[CandidateOut]:
    assert_org_member(user_id, organization_id)
    try:
        rows, total = await service.list_candidates(
            organization_id, status, search, country_code, page, page_size,
            sort_by, sort_direction
        )
        response.headers["X-Total-Count"] = str(total)
        if page is not None:
            response.headers["X-Page"] = str(page)
            response.headers["X-Page-Size"] = str(page_size)
        return [CandidateOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/duplicates", response_model=list[CandidateOut])
async def find_candidate_duplicates(
    organization_id: UUID,
    email: str | None = Query(default=None, max_length=320),
    phone: str | None = Query(default=None, max_length=50),
    exclude_candidate_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
) -> list[CandidateOut]:
    assert_org_member(user_id, organization_id)
    if not (email and email.strip()) and not (phone and phone.strip()):
        raise HTTPException(status_code=422, detail="Provide an email address or phone number to check for duplicates")
    try:
        rows = await service.find_duplicates(organization_id, email, phone, exclude_candidate_id)
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
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    assert_org_member(user_id, organization_id)
    try:
        row = await service.get_candidate(candidate_id, organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateOut.model_validate(row)


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: UUID,
    organization_id: UUID,
    payload: CandidateUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    assert_org_member(user_id, organization_id)
    try:
        row = await service.update_candidate(candidate_id, organization_id, payload)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateOut.model_validate(row)


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(
    candidate_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    assert_org_admin(user_id, organization_id)
    try:
        deleted = await service.delete_candidate(candidate_id, organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")
