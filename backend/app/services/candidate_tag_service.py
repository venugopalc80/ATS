from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.candidate_tags import CandidateTagCreate

TAG_COLUMNS = "id, organization_id, name, colour, created_by, created_at, updated_at"


class CandidateTagService:
    async def list_tags(self, organization_id: UUID, candidate_id: UUID | None = None) -> list[dict[str, Any]]:
        query = f"select {TAG_COLUMNS} from public.candidate_tags where organization_id = %s"
        params: list[Any] = [organization_id]
        if candidate_id is not None:
            query += """
              and exists (
                select 1 from public.candidate_tag_assignments a
                where a.organization_id = candidate_tags.organization_id
                  and a.tag_id = candidate_tags.id and a.candidate_id = %s
              )
            """
            params.append(candidate_id)
        query += " order by lower(name), id"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_tag(self, payload: CandidateTagCreate, user_id: UUID) -> dict[str, Any]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"insert into public.candidate_tags (organization_id, name, colour, created_by) values (%s, %s, %s, %s) returning {TAG_COLUMNS}",
                    [payload.organization_id, payload.name, payload.colour, user_id],
                )
                return cursor.fetchone()

    async def delete_tag(self, organization_id: UUID, tag_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.candidate_tags where organization_id = %s and id = %s",
                    [organization_id, tag_id],
                )
                return cursor.rowcount > 0

    async def assign_tag(self, organization_id: UUID, candidate_id: UUID, tag_id: UUID, user_id: UUID) -> dict[str, Any]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select exists(select 1 from public.candidates where id = %s and organization_id = %s) as candidate_ok, exists(select 1 from public.candidate_tags where id = %s and organization_id = %s) as tag_ok",
                    [candidate_id, organization_id, tag_id, organization_id],
                )
                found = cursor.fetchone()
                if not found["candidate_ok"] or not found["tag_ok"]:
                    raise ValueError("Candidate and tag must belong to the selected organisation")
                cursor.execute(
                    """insert into public.candidate_tag_assignments (organization_id, candidate_id, tag_id, assigned_by)
                       values (%s, %s, %s, %s)
                       on conflict (candidate_id, tag_id) do nothing
                       returning candidate_id, tag_id, organization_id, assigned_by, created_at""",
                    [organization_id, candidate_id, tag_id, user_id],
                )
                row = cursor.fetchone()
                if row is not None:
                    return row
                cursor.execute(
                    """select candidate_id, tag_id, organization_id, assigned_by, created_at
                       from public.candidate_tag_assignments
                       where organization_id = %s and candidate_id = %s and tag_id = %s""",
                    [organization_id, candidate_id, tag_id],
                )
                return cursor.fetchone()

    async def unassign_tag(self, organization_id: UUID, candidate_id: UUID, tag_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.candidate_tag_assignments where organization_id = %s and candidate_id = %s and tag_id = %s",
                    [organization_id, candidate_id, tag_id],
                )
                return cursor.rowcount > 0
