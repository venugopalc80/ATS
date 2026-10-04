from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate
from app.services.client_service import ClientService

router = APIRouter(prefix="/api/clients", tags=["clients"])
service = ClientService()

def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")

@router.get("", response_model=list[ClientOut])
async def list_clients(
    organization_id: UUID,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        rows = await service.list_clients(organization_id, status, search)
        return [ClientOut.model_validate(row) for row in rows]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.post("", response_model=ClientOut, status_code=201)
async def create_client(payload: ClientCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    try:
        return ClientOut.model_validate(await service.create_client(payload))
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        row = await service.get_client(client_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Client not found")
    assert_org_member(user_id, row["organization_id"])
    return ClientOut.model_validate(row)

@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(client_id: UUID, payload: ClientUpdate, user_id: UUID = Depends(get_current_user_id)):
    try:
        existing = await service.get_client(client_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Client not found")
        assert_org_member(user_id, existing["organization_id"])
        row = await service.update_client(client_id, payload)
        return ClientOut.model_validate(row)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc

@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        existing = await service.get_client(client_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Client not found")
        assert_org_member(user_id, existing["organization_id"])
        if not await service.delete_client(client_id):
            raise HTTPException(status_code=404, detail="Client not found")
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise db_unavailable(exc) from exc
