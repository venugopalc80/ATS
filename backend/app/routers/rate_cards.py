from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.rate_cards import RateCardCreate, RateCardOut, RateCardUpdate
from app.services.rate_card_service import RateCardService

router = APIRouter(prefix="/api/rate-cards", tags=["rate-cards"])
service = RateCardService()


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("", response_model=list[RateCardOut])
async def list_rate_cards(
    organization_id: UUID,
    client_id: UUID | None = None,
    status: str | None = Query(default=None, pattern=r"^(draft|active|expired|archived)$"),
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_rate_cards(organization_id, client_id, status, include_archived)
        return [RateCardOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("", response_model=RateCardOut, status_code=201)
async def create_rate_card(payload: RateCardCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        return RateCardOut.model_validate(await service.create_rate_card(payload, user_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.get("/{rate_card_id}", response_model=RateCardOut)
async def get_rate_card(
    rate_card_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        row = await service.get_rate_card(organization_id, rate_card_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    return RateCardOut.model_validate(row)


@router.patch("/{rate_card_id}", response_model=RateCardOut)
async def update_rate_card(
    rate_card_id: UUID,
    payload: RateCardUpdate,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        row = await service.update_rate_card(organization_id, rate_card_id, payload, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    return RateCardOut.model_validate(row)
