from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
service = CandidateService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


def _can_read_contact(user_id: UUID, organization_id: UUID) -> bool:
    try:
        require_permission(user_id, organization_id, "candidate.read_contact")
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise


def _candidate_output(row: dict, include_contact: bool) -> CandidateOut:
    candidate = CandidateOut.model_validate(row)
    if not include_contact:
        candidate = candidate.model_copy(update={"email": None, "phone": None})
    return candidate


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    organization_id: UUID,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    user_id: UUID = Depends(get_current_user_id),
) -> list[CandidateOut]:
    require_permission(user_id, organization_id, "candidate.read_basic")
    include_contact = _can_read_contact(user_id, organization_id)
    try:
        rows = await service.list_candidates(
            organization_id, status, search, include_contact_search=include_contact
        )
        return [_candidate_output(row, include_contact) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=CandidateOut, status_code=201)
async def create_candidate(
    payload: CandidateCreate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    require_permission(user_id, payload.organization_id, "candidate.create")
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
        organization_id = await service.get_candidate_organization_id(candidate_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        require_permission(user_id, organization_id, "candidate.read_basic")
        include_contact = _can_read_contact(user_id, organization_id)
        row = await service.get_candidate(candidate_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return _candidate_output(row, include_contact)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    user_id: UUID = Depends(get_current_user_id),
) -> CandidateOut:
    try:
        organization_id = await service.get_candidate_organization_id(candidate_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        require_permission(user_id, organization_id, "candidate.update")
        row = await service.update_candidate(candidate_id, payload)
        if row is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        include_contact = _can_read_contact(user_id, organization_id)
        return _candidate_output(row, include_contact)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(
    candidate_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    try:
        organization_id = await service.get_candidate_organization_id(candidate_id)
        if organization_id is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        require_permission(user_id, organization_id, "candidate.delete")
        deleted = await service.delete_candidate(candidate_id)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found")
