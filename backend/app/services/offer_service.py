from uuid import UUID

from fastapi import HTTPException

from app.db import get_connection
from app.schemas.offers import OfferCreate, OfferUpdate

ALLOWED_OFFER_TRANSITIONS = {
    "draft": {"sent", "withdrawn"},
    "sent": {"accepted", "rejected", "withdrawn", "expired"},
    "accepted": set(),
    "rejected": set(),
    "withdrawn": set(),
    "expired": set(),
}


def list_offers(organization_id: UUID, status: str | None = None):
    with get_connection() as c:
        with c.cursor() as cur:
            if status:
                cur.execute("select * from public.offers where organization_id=%s and status=%s order by created_at desc", [organization_id, status])
            else:
                cur.execute("select * from public.offers where organization_id=%s order by created_at desc", [organization_id])
            return cur.fetchall()


def create_offer(payload: OfferCreate, user_id: UUID):
    d = payload.model_dump()
    d["created_by"] = user_id
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select 1 from public.applications where id=%s and organization_id=%s", [payload.application_id, payload.organization_id])
            if cur.fetchone() is None:
                raise ValueError("Application must belong to the same organization")
            cur.execute(
                """insert into public.offers
                (organization_id,application_id,title,status,employment_type,start_date,salary_amount,salary_currency,bonus_amount,benefits,expires_at,notes,created_by)
                values (%(organization_id)s,%(application_id)s,%(title)s,%(status)s,%(employment_type)s,%(start_date)s,%(salary_amount)s,%(salary_currency)s,%(bonus_amount)s,%(benefits)s,%(expires_at)s,%(notes)s,%(created_by)s)
                returning *""",
                d,
            )
            row = cur.fetchone()
        c.commit()
        return row


def get_offer(organization_id: UUID, offer_id: UUID):
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select * from public.offers where id=%s and organization_id=%s", [offer_id, organization_id])
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Offer not found")
            return row


def update_offer(organization_id: UUID, offer_id: UUID, payload: OfferUpdate, actor_user_id: UUID):
    d = payload.model_dump(exclude_unset=True)
    if not d:
        return get_offer(organization_id, offer_id)

    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select status from public.offers where id=%s and organization_id=%s", [offer_id, organization_id])
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(404, "Offer not found")

            if "status" in d:
                current_status = existing["status"]
                next_status = d["status"]
                if next_status != current_status and next_status not in ALLOWED_OFFER_TRANSITIONS.get(current_status, set()):
                    raise HTTPException(409, "Invalid offer status transition")
                if next_status == "sent" and next_status != current_status:
                    d["sent_at"] = "now()"
                elif next_status in {"accepted", "rejected", "withdrawn", "expired"} and next_status != current_status:
                    d["responded_at"] = "now()"

            assignments = []
            values = {}
            for key, value in d.items():
                if value == "now()" and key in {"sent_at", "responded_at"}:
                    assignments.append(f"{key}=now()")
                else:
                    assignments.append(f"{key}=%({key})s")
                    values[key] = value
            values.update({"offer_id": offer_id, "organization_id": organization_id})

            cur.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
            cur.execute(
                f"update public.offers set {', '.join(assignments)},updated_at=now() where id=%(offer_id)s and organization_id=%(organization_id)s returning *",
                values,
            )
            row = cur.fetchone()
        c.commit()
        return row
