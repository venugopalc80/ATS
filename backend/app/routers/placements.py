from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from app.auth import assert_org_member, get_current_user_id
from app.schemas.placements import PlacementCreate, PlacementOut, PlacementUpdate
from app.services.placement_service import create_placement,get_placement,list_placements,update_placement
router=APIRouter(prefix="/api/placements",tags=["placements"])
@router.get("",response_model=list[PlacementOut])
def get_placements(organization_id: UUID,status_filter: str|None=Query(None,alias="status"),user_id: UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id); return list_placements(organization_id,status_filter)
@router.post("",response_model=PlacementOut,status_code=status.HTTP_201_CREATED)
def post_placement(payload: PlacementCreate,user_id: UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,payload.organization_id); return create_placement(payload,user_id)
@router.get("/{placement_id}",response_model=PlacementOut)
def get_one(placement_id: UUID,organization_id: UUID,user_id: UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id); return get_placement(organization_id,placement_id)
@router.patch("/{placement_id}",response_model=PlacementOut)
def patch_placement(placement_id: UUID,payload: PlacementUpdate,organization_id: UUID,user_id: UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id); return update_placement(organization_id,placement_id,payload)
