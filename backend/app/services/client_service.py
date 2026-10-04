from typing import Any
from uuid import UUID
from app.db import get_connection
from app.schemas.clients import ClientCreate, ClientUpdate

CLIENT_COLUMNS = """
    id, organization_id, name, website, industry, country_code,
    contact_name, contact_email, contact_phone, status, created_at, updated_at
"""

class ClientService:
    async def list_clients(self, organization_id: UUID, status: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        query = f"select {CLIENT_COLUMNS} from public.clients where organization_id = %s"
        params: list[Any] = [organization_id]
        if status:
            query += " and status = %s"
            params.append(status)
        if search:
            query += " and (name ilike %s or contact_name ilike %s or industry ilike %s)"
            term = f"%{search}%"
            params.extend([term, term, term])
        query += " order by name asc"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_client(self, payload: ClientCreate) -> dict[str, Any]:
        data = payload.model_dump(mode="python")
        columns = list(data.keys())
        values = [data[c] for c in columns]
        placeholders = ", ".join(["%s"] * len(columns))
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"insert into public.clients ({', '.join(columns)}) values ({placeholders}) returning {CLIENT_COLUMNS}",
                    values,
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Client was not created")
                return row

    async def get_client(self, client_id: UUID) -> dict[str, Any] | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select {CLIENT_COLUMNS} from public.clients where id = %s", [client_id])
                return cursor.fetchone()

    async def update_client(self, client_id: UUID, payload: ClientUpdate) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_client(client_id)
        assignments = ", ".join(f"{c} = %s" for c in data)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"update public.clients set {assignments}, updated_at = now() where id = %s returning {CLIENT_COLUMNS}",
                    list(data.values()) + [client_id],
                )
                return cursor.fetchone()

    async def delete_client(self, client_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from public.clients where id = %s", [client_id])
                return cursor.rowcount > 0
