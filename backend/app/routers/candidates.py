from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_permission, assert_resource_access, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
service = CandidateService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    organization_id: UUID,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    user_id: UUID = Depends(get_current_user_id),
) -> list[CandidateOut]:
    assert_org_permission(user_id, organization_id, "candidates.read")
    try:
        rows = await service.list_candidates(organization_id, status, search, user_id)
        return [CandidateOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc



@router.get("/search")
async def search_candidates(
    organization_id: UUID,
    status: str | None = Query(default=None, pattern="^(active|inactive|placed|do_not_contact)$"),
    search: str | None = Query(default=None, max_length=100),
    country_code: str | None = Query(default=None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    skill: str | None = Query(default=None, max_length=80),
    min_experience: float | None = Query(default=None, ge=0, le=80),
    max_experience: float | None = Query(default=None, ge=0, le=80),
    sort_by: str = Query(default="created_at", pattern="^(name|title|location|experience|created_at)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    assert_org_permission(user_id, organization_id, "candidates.read")
    if min_experience is not None and max_experience is not None and min_experience > max_experience:
        raise HTTPException(status_code=422, detail="min_experience cannot exceed max_experience")
    try:
        result = await service.search_candidates(
            organization_id,
            user_id,
            status=status,
            search=search,
            country_code=country_code,
            skill=skill,
            min_experience=min_experience,
            max_experience=max_experience,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )
        result["items"] = [CandidateOut.model_validate(row) for row in result["items"]]
        return result
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=CandidateOut, status_code=201)
async def create_candidate(
    payload: CandidateCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    assert_org_permission(user_id, payload.organization_id, "candidates.create")
    try:
        row = await service.create_candidate(payload, user_id)
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
    assert_org_permission(user_id, row["organization_id"], "candidates.read")
    assert_resource_access(user_id, row["organization_id"], "candidate", candidate_id)
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
        assert_org_permission(user_id, existing["organization_id"], "candidates.update")
        assert_resource_access(user_id, existing["organization_id"], "candidate", candidate_id)
        row = await service.update_candidate(candidate_id, payload)
        return CandidateOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        assert_org_permission(user_id, existing["organization_id"], "candidates.delete")
        assert_resource_access(user_id, existing["organization_id"], "candidate", candidate_id)
        deleted = await service.delete_candidate(candidate_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")
