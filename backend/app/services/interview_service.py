from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.interviews import InterviewCreate, InterviewUpdate

COLUMNS = "id, organization_id, application_id, scheduled_at, duration_minutes, interview_type, location, interviewer_ids, status, notes, feedback, outcome, created_by, created_at, updated_at"

ALLOWED_INTERVIEW_TRANSITIONS = {
    "scheduled": {"completed", "cancelled", "rescheduled", "no_show"},
    "rescheduled": {"scheduled", "cancelled", "no_show"},
    "completed": set(),
    "cancelled": set(),
    "no_show": set(),
}


def _validate_interviewer_membership(cursor: Any, organization_id: UUID, interviewer_ids: list[UUID]) -> None:
    """Prevent scheduling users who are not members of the interview's organisation."""
    if not interviewer_ids:
        return

    cursor.execute(
        """
        select user_id
        from public.organization_members
        where organization_id = %s and user_id = any(%s)
        """,
        [organization_id, interviewer_ids],
    )
    member_ids = {UUID(str(row["user_id"])) for row in cursor.fetchall()}
    if member_ids != set(interviewer_ids):
        raise ValueError("All interviewers must belong to the same organization")


class InterviewService:
    async def list_interviews(self, organization_id: UUID, status: str | None = None):
        query = f"select {COLUMNS} from public.interviews where organization_id=%s"
        params: list[Any] = [organization_id]
        if status:
            query += " and status=%s"
            params.append(status)
        query += " order by scheduled_at asc"
        with get_connection() as c:
            with c.cursor() as cur:
                cur.execute(query, params)
                return list(cur.fetchall())

    async def create_interview(self, payload: InterviewCreate, created_by: UUID):
        d = payload.model_dump()
        d["created_by"] = created_by
        cols = list(d)
        vals = [d[x] for x in cols]
        with get_connection() as c:
            with c.cursor() as cur:
                cur.execute(
                    "select 1 from public.applications where id=%s and organization_id=%s",
                    [payload.application_id, payload.organization_id],
                )
                if cur.fetchone() is None:
                    raise ValueError("Application must belong to the same organization")
                _validate_interviewer_membership(cur, payload.organization_id, payload.interviewer_ids)
                cur.execute(
                    f"insert into public.interviews ({','.join(cols)}) values ({','.join(['%s'] * len(cols))}) returning {COLUMNS}",
                    vals,
                )
                return cur.fetchone()

    async def get_interview(self, interview_id: UUID):
        with get_connection() as c:
            with c.cursor() as cur:
                cur.execute(
                    f"select {COLUMNS} from public.interviews where id=%s",
                    [interview_id],
                )
                return cur.fetchone()

    async def update_interview(self, interview_id: UUID, payload: InterviewUpdate, actor_user_id: UUID):
        d = payload.model_dump(exclude_unset=True)
        if not d:
            return await self.get_interview(interview_id)

        with get_connection() as c:
            with c.cursor() as cur:
                cur.execute(
                    "select organization_id, status from public.interviews where id=%s",
                    [interview_id],
                )
                existing = cur.fetchone()
                if existing is None:
                    return None

                if "status" in d:
                    current_status = existing["status"]
                    next_status = d["status"]
                    if (
                        next_status != current_status
                        and next_status not in ALLOWED_INTERVIEW_TRANSITIONS.get(current_status, set())
                    ):
                        raise ValueError("Invalid interview status transition")

                if "interviewer_ids" in d and d["interviewer_ids"] is not None:
                    _validate_interviewer_membership(cur, existing["organization_id"], d["interviewer_ids"])

                cur.execute(
                    "select set_config('app.actor_user_id', %s, true)",
                    [str(actor_user_id)],
                )
                cur.execute(
                    f"update public.interviews set {','.join(f'{k}=%s' for k in d)},updated_at=now() where id=%s returning {COLUMNS}",
                    list(d.values()) + [interview_id],
                )
                return cur.fetchone()
