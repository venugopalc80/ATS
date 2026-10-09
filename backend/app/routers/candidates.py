from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

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
