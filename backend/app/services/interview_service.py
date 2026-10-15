from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.interviews import InterviewCreate, InterviewUpdate

COLUMNS = "id, organization_id, application_id, scheduled_at, duration_minutes, interview_type, location, interviewer_ids, status, notes, feedback, outcome, feedback_author_id, feedback_at, created_by, created_at, updated_at"

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
                cur.execute("select 1 from public.applications where id=%s and organization_id=%s", [payload.application_id, payload.organization_id])
                if cur.fetchone() is None:
                    raise ValueError("Application must belong to the same organization")
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
                # Lock the row while validating the transition and attributing feedback.
                cur.execute(
                    "select status, feedback from public.interviews where id=%s for update",
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

                # Only a change to the feedback text updates its author/timestamp.
                # Clearing feedback clears attribution; an unchanged feedback value
                # preserves the original author and timestamp.
                if "feedback" in d and d["feedback"] != existing.get("feedback"):
                    has_feedback = bool(d["feedback"] and d["feedback"].strip())
                    d["feedback_author_id"] = actor_user_id if has_feedback else None
                    d["feedback_at"] = has_feedback

                cur.execute(
                    "select set_config('app.actor_user_id', %s, true)",
                    [str(actor_user_id)],
                )
                assignments = []
                params = []
                for key, value in d.items():
                    if key == "feedback_at":
                        assignments.append("feedback_at=now()" if value else "feedback_at=NULL")
                    else:
                        assignments.append(f"{key}=%s")
                        params.append(value)
                cur.execute(
                    f"update public.interviews set {','.join(assignments)},updated_at=now() where id=%s returning {COLUMNS}",
                    params + [interview_id],
                )
                return cur.fetchone()
