from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.candidates import CandidateCreate, CandidateUpdate


CANDIDATE_COLUMNS = """
    id, organization_id, first_name, last_name, email, phone,
    city, region, country_code, status, current_title,
    years_experience, skills, resume_path, resume_text,
    ai_summary, consent_recorded_at, consent_purpose,
    retention_until, created_at, updated_at
"""


class CandidateService:
    async def list_candidates(
        self,
        organization_id: UUID,
        status: str | None = None,
        search: str | None = None,
        country_code: str | None = None,
        page: int | None = None,
        page_size: int = 25,
        sort_by: str = "name",
        sort_direction: str = "asc",
    ) -> tuple[list[dict[str, Any]], int]:
        where = " where organization_id = %s"
        params: list[Any] = [organization_id]
        if status:
            where += " and status = %s"
            params.append(status)
        if country_code:
            where += " and upper(coalesce(country_code, '')) = %s"
            params.append(country_code.upper())
        if search and search.strip():
            where += """
                and (
                    first_name ilike %s or coalesce(last_name, '') ilike %s
                    or coalesce(email, '') ilike %s or coalesce(current_title, '') ilike %s
                    or coalesce(city, '') ilike %s or coalesce(region, '') ilike %s
                    or array_to_string(skills, ' ') ilike %s or id::text ilike %s
                )
            """
            term = f"%{search.strip()}%"
            params.extend([term] * 8)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) as total from public.candidates" + where, params)
                total_row = cursor.fetchone()
                total = int(total_row["total"] if total_row else 0)
                query = f"select {CANDIDATE_COLUMNS} from public.candidates" + where
                sort_columns = {
                    "name": "lower(first_name), lower(coalesce(last_name, ''))",
                    "title": "lower(coalesce(current_title, ''))",
                    "location": "lower(coalesce(city, '')), lower(coalesce(region, ''))",
                    "status": "status",
                }
                order_by = sort_columns.get(sort_by, sort_columns["name"])
                direction = "DESC" if sort_direction.lower() == "desc" else "ASC"
                query += f" order by {order_by} {direction}, id asc"
                query_params = list(params)
                if page is not None:
                    query += " limit %s offset %s"
                    query_params.extend([page_size, (page - 1) * page_size])
                cursor.execute(query, query_params)
                return list(cursor.fetchall()), total

    async def find_duplicates(
        self,
        organization_id: UUID,
        email: str | None = None,
        phone: str | None = None,
        exclude_candidate_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = [organization_id]
        normalized_email = email.strip().casefold() if email and email.strip() else None
        normalized_phone = "".join(char for char in phone if char.isdigit()) if phone else ""
        if normalized_email:
            clauses.append("lower(trim(email)) = %s")
            params.append(normalized_email)
        if normalized_phone:
            clauses.append("regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g') = %s")
            params.append(normalized_phone)
        if not clauses:
            return []
        query = f"""
            select {CANDIDATE_COLUMNS} from public.candidates
            where organization_id = %s and ({" or ".join(clauses)})
        """
        if exclude_candidate_id:
            query += " and id <> %s"
            params.append(exclude_candidate_id)
        query += " order by created_at desc limit 10"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_candidate(self, payload: CandidateCreate) -> dict[str, Any]:
        data = payload.model_dump(mode="python")
        columns = list(data.keys())
        values = [data[column] for column in columns]
        placeholders = ", ".join(["%s"] * len(columns))
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"insert into public.candidates ({', '.join(columns)}) values ({placeholders}) returning {CANDIDATE_COLUMNS}",
                    values,
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Candidate was not created")
                return row

    async def get_candidate(self, candidate_id: UUID, organization_id: UUID) -> dict[str, Any] | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {CANDIDATE_COLUMNS} from public.candidates where id = %s and organization_id = %s",
                    [candidate_id, organization_id],
                )
                return cursor.fetchone()

    async def update_candidate(
        self, candidate_id: UUID, organization_id: UUID, payload: CandidateUpdate
    ) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_candidate(candidate_id, organization_id)
        assignments = ", ".join(f"{column} = %s" for column in data)
        values = list(data.values()) + [candidate_id, organization_id]
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"update public.candidates set {assignments}, updated_at = now() where id = %s and organization_id = %s returning {CANDIDATE_COLUMNS}",
                    values,
                )
                return cursor.fetchone()

    async def delete_candidate(self, candidate_id: UUID, organization_id: UUID) -> bool:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.candidates where id = %s and organization_id = %s",
                    [candidate_id, organization_id],
                )
                return cursor.rowcount > 0
