from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from app.auth import get_current_user_id, require_permission
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.offers import OfferCreate, OfferOut, OfferUpdate
from app.services.offer_service import create_offer, get_offer, list_offers, update_offer

router = APIRouter(prefix="/api/offers", tags=["offers"])

def _offer_output(row, include_salary: bool) -> OfferOut:
    offer = OfferOut.model_validate(row)
    if not include_salary:
        offer = offer.model_copy(update={"salary_amount": None, "salary_currency": None, "bonus_amount": None})
    return offer

def _include_salary(user_id: UUID, organization_id: UUID) -> bool:
    try:
        require_permission(user_id, organization_id, "offer.salary.read")
        return True
    except HTTPException as exc:
        if exc.status_code == 403:
            return False
        raise

def _require_offer_write(user_id: UUID, organization_id: UUID, payload) -> None:
    salary_fields = {"salary_amount", "salary_currency", "bonus_amount"}
    require_permission(user_id, organization_id, "offer.manage")
    if salary_fields.intersection(payload.model_fields_set):
        require_permission(user_id, organization_id, "offer.salary.manage")

@router.get("", response_model=list[OfferOut])
def get_offers(organization_id: UUID, status_filter: str | None = Query(None, alias="status"), candidate_id: UUID | None = Query(None), user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, organization_id, "offer.read")
    include_salary = _include_salary(user_id, organization_id)
    try:
        return [_offer_output(row, include_salary) for row in list_offers(organization_id, status_filter, candidate_id)]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def post_offer(payload: OfferCreate, user_id: UUID = Depends(get_current_user_id)):
    _require_offer_write(user_id, payload.organization_id, payload)
    try:
        row = create_offer(payload, user_id)
        return _offer_output(row, _include_salary(user_id, payload.organization_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

@router.get("/{offer_id}", response_model=OfferOut)
def get_one(offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    require_permission(user_id, organization_id, "offer.read")
    include_salary = _include_salary(user_id, organization_id)
    try:
        return _offer_output(get_offer(organization_id, offer_id), include_salary)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc

@router.patch("/{offer_id}", response_model=OfferOut)
def patch_offer(offer_id: UUID, payload: OfferUpdate, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    _require_offer_write(user_id, organization_id, payload)
    try:
        row = update_offer(organization_id, offer_id, payload, user_id)
        return _offer_output(row, _include_salary(user_id, organization_id))
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(503, "Database operation failed") from exc
