from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from app.auth import assert_org_permission, assert_resource_access, get_current_user_id
from app.schemas.offers import OfferCreate, OfferOut, OfferUpdate
from app.services.offer_service import create_offer,get_offer,list_offers,update_offer
router=APIRouter(prefix="/api/offers",tags=["offers"])
@router.get("",response_model=list[OfferOut])
def get_offers(organization_id: UUID,status_filter: str|None=Query(None,alias="status"),user_id: UUID=Depends(get_current_user_id)):
    assert_org_permission(user_id,organization_id, "offers.read"); return list_offers(organization_id,user_id,status_filter)
@router.post("",response_model=OfferOut,status_code=status.HTTP_201_CREATED)
def post_offer(payload: OfferCreate,user_id: UUID=Depends(get_current_user_id)):
    assert_org_permission(user_id,payload.organization_id, "offers.create")
    assert_resource_access(user_id, payload.organization_id, "application", payload.application_id)
    try:return create_offer(payload,user_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
@router.get("/{offer_id}",response_model=OfferOut)
def get_one(offer_id: UUID,organization_id: UUID,user_id: UUID=Depends(get_current_user_id)):
    assert_org_permission(user_id,organization_id, "offers.read")
    row = get_offer(organization_id,offer_id)
    assert_resource_access(user_id, organization_id, "application", row["application_id"])
    return row
@router.patch("/{offer_id}",response_model=OfferOut)
def patch_offer(offer_id: UUID,payload: OfferUpdate,organization_id: UUID,user_id: UUID=Depends(get_current_user_id)):
    assert_org_permission(user_id,organization_id, "offers.update")
    row = get_offer(organization_id, offer_id)
    assert_resource_access(user_id, organization_id, "application", row["application_id"])
    return update_offer(organization_id,offer_id,payload,user_id)
