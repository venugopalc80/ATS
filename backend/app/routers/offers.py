from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.schemas.offer_management import (
    OfferApprovalDecision, OfferApprovalOut, OfferCandidateResponse, OfferVersionOut,
)
from app.schemas.offers import OfferCreate, OfferOut, OfferUpdate
from app.services.offer_management_service import (
    decide_approval, issue_offer, list_approvals, list_versions,
    record_candidate_response, submit_for_approval,
)
from app.services.offer_service import create_offer, get_offer, list_offers, update_offer

router = APIRouter(prefix="/api/offers", tags=["offers"])
APPROVER_ROLES = {"owner", "admin"}
OFFER_MANAGER_ROLES = {"owner", "admin", "recruiter", "hiring_manager"}


def _require_role(user_id: UUID, organization_id: UUID, roles: set[str]) -> None:
    role = get_org_role(user_id, organization_id)
    if role not in roles:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this offer action")


@router.get("", response_model=list[OfferOut])
def get_offers(
    organization_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    return list_offers(organization_id, status_filter)


@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def post_offer(payload: OfferCreate, user_id: UUID = Depends(get_current_user_id)):
    _require_role(user_id, payload.organization_id, OFFER_MANAGER_ROLES)
    try:
        return create_offer(payload, user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{offer_id}", response_model=OfferOut)
def get_one(offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    return get_offer(organization_id, offer_id)


@router.patch("/{offer_id}", response_model=OfferOut)
def patch_offer(
    offer_id: UUID, payload: OfferUpdate, organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    _require_role(user_id, organization_id, OFFER_MANAGER_ROLES)
    return update_offer(organization_id, offer_id, payload, user_id)


@router.post("/{offer_id}/submit-for-approval", response_model=OfferOut)
def submit_offer_for_approval(
    offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id),
):
    _require_role(user_id, organization_id, OFFER_MANAGER_ROLES)
    return submit_for_approval(organization_id, offer_id, user_id)


@router.post("/{offer_id}/approval", response_model=dict)
def approve_offer(
    offer_id: UUID, organization_id: UUID, payload: OfferApprovalDecision,
    user_id: UUID = Depends(get_current_user_id),
):
    _require_role(user_id, organization_id, APPROVER_ROLES)
    return decide_approval(organization_id, offer_id, user_id, payload)


@router.post("/{offer_id}/issue", response_model=OfferOut)
def issue_approved_offer(
    offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id),
):
    _require_role(user_id, organization_id, OFFER_MANAGER_ROLES)
    return issue_offer(organization_id, offer_id, user_id)


@router.post("/{offer_id}/record-candidate-response", response_model=OfferOut)
def record_response(
    offer_id: UUID, organization_id: UUID, payload: OfferCandidateResponse,
    user_id: UUID = Depends(get_current_user_id),
):
    _require_role(user_id, organization_id, OFFER_MANAGER_ROLES)
    return record_candidate_response(organization_id, offer_id, user_id, payload)


@router.get("/{offer_id}/versions", response_model=list[OfferVersionOut])
def get_versions(
    offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    return list_versions(organization_id, offer_id)


@router.get("/{offer_id}/approvals", response_model=list[OfferApprovalOut])
def get_approvals(
    offer_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    return list_approvals(organization_id, offer_id)
