from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/candidates", tags=["candidates"])


@router.get("")
async def list_candidates(organization_id: str) -> dict:
    return {"items": [], "organization_id": organization_id}
