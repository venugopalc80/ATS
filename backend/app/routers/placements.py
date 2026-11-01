from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.placements import PlacementCreate, PlacementOut, PlacementUpdate
from app.services.placement_service import create_placement, get_placement, list_placements, update_placement

router = APIRouter(prefix="/api/placements", tags=["placements"])
FEE_FIELDS = {"fee_amount", "fee_currency", "fee_type", "fee_percentage"}


def _require_placement_write(user_id: UUID, organization_id: UUID, payload) -> None:
    require_permission(user_id, organization_id, "placement.manage")
    if FEE_FIELDS.intersection(payload.model_fields_set):
        require_permission(user_id, organization_id, "placement.fee.manage")


def _placement_output(row, user_id: UUID, organization_id: UUID) -> PlacementOut:
    try:
        require_permission(user_id, organization_id, "placement.fee.read")
        include_fees = True
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        include_fees = False

    output = PlacementOut.model_validate(row)
    if not include_fees:
        output = output.model_copy(update={
            "fee_amount": None,
            "fee_currency": None,
            "fee_type": None,
            "fee_percentage": None,
        })
    return output


@router.get("", response_model=list[PlacementOut])
def get_placements(organization_id: UUID, status_filter: str | None = Query(None, alias="status"), candidate_id: UUID | None = Query(None), user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, organization_id, "placement.read")
    try:
        return [_placement_output(row, user_id, organization_id) for row in list_placements(organization_id, status_filter, candidate_id)]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc


@router.post("", response_model=PlacementOut, status_code=status.HTTP_201_CREATED)
def post_placement(payload: PlacementCreate, user_id: UUID = Depends(get_current_user_id)):
    _require_placement_write(user_id, payload.organization_id, payload)
    try:
        row = create_placement(payload, user_id)
        return _placement_output(row, user_id, payload.organization_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc


@router.get("/{placement_id}", response_model=PlacementOut)
def get_one(placement_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, organization_id, "placement.read")
    try:
        row = get_placement(organization_id, placement_id)
        return _placement_output(row, user_id, organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc


@router.patch("/{placement_id}", response_model=PlacementOut)
def patch_placement(placement_id: UUID, payload: PlacementUpdate, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    _require_placement_write(user_id, organization_id, payload)
    try:
        row = update_placement(organization_id, placement_id, payload, user_id)
        return _placement_output(row, user_id, organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc
