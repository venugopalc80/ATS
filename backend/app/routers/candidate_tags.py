from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.errors import UniqueViolation

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.candidate_tags import CandidateTagAssignmentOut, CandidateTagCreate, CandidateTagOut
from app.services.candidate_tag_service import CandidateTagService

router = APIRouter(prefix="/api/candidate-tags", tags=["candidate-tags"])
service = CandidateTagService()


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[CandidateTagOut])
async def list_tags(
    organization_id: UUID,
    candidate_id: UUID | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    if candidate_id is not None:
        # Verify candidate membership before returning candidate-specific tag data.
        from app.services.candidate_service import CandidateService
        try:
            candidate = await CandidateService().get_candidate(candidate_id)
        except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
            raise db_unavailable(exc) from exc
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        if candidate["organization_id"] != organization_id:
            raise HTTPException(status_code=404, detail="Candidate not found")
    try:
        return [CandidateTagOut.model_validate(row) for row in await service.list_tags(organization_id, candidate_id)]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.post("", response_model=CandidateTagOut, status_code=201)
async def create_tag(payload: CandidateTagCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        row = await service.create_tag(payload, user_id)
        return CandidateTagOut.model_validate(row)
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A tag with this name already exists in this organisation") from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        if not await service.delete_tag(organization_id, tag_id):
            raise HTTPException(status_code=404, detail="Tag not found")
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.put("/{tag_id}/candidates/{candidate_id}", response_model=CandidateTagAssignmentOut)
async def assign_tag(
    tag_id: UUID,
    candidate_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        row = await service.assign_tag(organization_id, candidate_id, tag_id, user_id)
        return CandidateTagAssignmentOut.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc


@router.delete("/{tag_id}/candidates/{candidate_id}", status_code=204)
async def unassign_tag(
    tag_id: UUID,
    candidate_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        if not await service.unassign_tag(organization_id, candidate_id, tag_id):
            raise HTTPException(status_code=404, detail="Tag assignment not found")
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
