from uuid import UUID

from fastapi import HTTPException

from app.db import get_connection
from app.schemas.placements import PlacementCreate, PlacementUpdate

ALLOWED_PLACEMENT_TRANSITIONS = {
    "pending": {"active", "cancelled"},
    "active": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def list_placements(organization_id: UUID, status: str | None = None):
    with get_connection() as c:
        with c.cursor() as cur:
            q = "select * from public.placements where organization_id=%s"
            args = [organization_id]
            if status:
                q += " and status=%s"
                args.append(status)
            q += " order by start_date desc"
            cur.execute(q, args)
            return cur.fetchall()


def create_placement(payload: PlacementCreate, user_id: UUID):
    d = payload.model_dump()
    d["created_by"] = user_id
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute(
                """select 1 from public.applications where id=%(application_id)s and organization_id=%(organization_id)s
                """,
                {"application_id": payload.application_id, "organization_id": payload.organization_id},
            )
            if cur.fetchone() is None:
                raise ValueError("Application must belong to the same organization")
            cur.execute(
                """insert into public.placements
                (organization_id,application_id,offer_id,job_id,candidate_id,client_id,status,start_date,end_date,fee_amount,fee_currency,fee_type,fee_percentage,notes,created_by)
                values (%(organization_id)s,%(application_id)s,%(offer_id)s,%(job_id)s,%(candidate_id)s,%(client_id)s,%(status)s,%(start_date)s,%(end_date)s,%(fee_amount)s,%(fee_currency)s,%(fee_type)s,%(fee_percentage)s,%(notes)s,%(created_by)s)
                returning *""",
                d,
            )
            row = cur.fetchone()
        c.commit()
        return row


def get_placement(organization_id: UUID, placement_id: UUID):
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select * from public.placements where id=%s and organization_id=%s", [placement_id, organization_id])
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Placement not found")
            return row


def update_placement(organization_id: UUID, placement_id: UUID, payload: PlacementUpdate, actor_user_id: UUID):
    d = payload.model_dump(exclude_unset=True)
    if not d:
        return get_placement(organization_id, placement_id)

    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select status, start_date, end_date from public.placements where id=%s and organization_id=%s", [placement_id, organization_id])
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(404, "Placement not found")

            if "status" in d:
                current_status = existing["status"]
                next_status = d["status"]
                if next_status != current_status and next_status not in ALLOWED_PLACEMENT_TRANSITIONS.get(current_status, set()):
                    raise HTTPException(409, "Invalid placement status transition")

            start_date = d.get("start_date", existing["start_date"])
            end_date = d.get("end_date", existing["end_date"])
            if end_date is not None and start_date is not None and end_date < start_date:
                raise HTTPException(422, "Placement end date cannot be before start date")

            assignments = ", ".join(f"{key}=%({key})s" for key in d)
            values = dict(d)
            values.update({"placement_id": placement_id, "organization_id": organization_id})

            cur.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
            cur.execute(
                f"update public.placements set {assignments},updated_at=now() where id=%(placement_id)s and organization_id=%(organization_id)s returning *",
                values,
            )
            row = cur.fetchone()
        c.commit()
        return row
