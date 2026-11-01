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
    ) -> list[dict[str, Any]]:
        query = f"""
            select {CANDIDATE_COLUMNS}
            from public.candidates
            where organization_id = %s
        """
        params: list[Any] = [organization_id]

        if status:
            query += " and status = %s"
            params.append(status)

        if search:
            query += """
                and (
                    first_name ilike %s
                    or coalesce(last_name, '') ilike %s
                    or coalesce(email, '') ilike %s
                    or coalesce(current_title, '') ilike %s
                    or coalesce(city, '') ilike %s
                )
            """
            term = f"%{search}%"
            params.extend([term, term, term, term, term])

        query += " order by created_at desc"

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
                    f"""
                    insert into public.candidates ({", ".join(columns)})
                    values ({placeholders})
                    returning {CANDIDATE_COLUMNS}
                    """,
                    values,
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("Candidate was not created")
                return row

    async def get_candidate_for_member(
        self, candidate_id: UUID, user_id: UUID
    ) -> dict[str, Any] | None:
        """Only return candidate data to a member of the candidate's organisation."""
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select {CANDIDATE_COLUMNS}
                    from public.candidates c
                    where c.id = %s
                      and exists (
                          select 1
                          from public.organization_members om
                          where om.organization_id = c.organization_id
                            and om.user_id = %s
                      )
                    """,
                    [candidate_id, user_id],
                )
                return cursor.fetchone()

    async def update_candidate(
        self,
        candidate_id: UUID,
        organization_id: UUID,
        payload: CandidateUpdate,
    ) -> dict[str, Any] | None:
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        select {CANDIDATE_COLUMNS}
                        from public.candidates
                        where id = %s and organization_id = %s
                        """,
                        [candidate_id, organization_id],
                    )
                    return cursor.fetchone()

        assignments = ", ".join(f"{column} = %s" for column in data)
        values = list(data.values()) + [candidate_id, organization_id]

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.candidates
                    set {assignments}, updated_at = now()
                    where id = %s and organization_id = %s
                    returning {CANDIDATE_COLUMNS}
                    """,
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
