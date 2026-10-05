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
                cur.execute("select status from public.interviews where id=%s", [interview_id])
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

                cur.execute(
                    "select set_config('app.actor_user_id', %s, true)",
                    [str(actor_user_id)],
                )
                cur.execute(
                    f"update public.interviews set {','.join(f'{k}=%s' for k in d)},updated_at=now() where id=%s returning {COLUMNS}",
                    list(d.values()) + [interview_id],
                )
                return cur.fetchone()
