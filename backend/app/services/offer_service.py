from uuid import UUID

from fastapi import HTTPException

from app.db import get_connection
from app.schemas.offers import OfferCreate, OfferUpdate

COMMERCIAL_OFFER_FIELDS = {"title", "employment_type", "start_date", "salary_amount", "salary_currency", "bonus_amount", "benefits", "expires_at"}

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
            cur.execute("select status from public.applications where id=%s and organization_id=%s for update", [payload.application_id, payload.organization_id])
            application = cur.fetchone()
            if application is None:
                raise ValueError("Application must belong to the same organization")
            if application["status"] not in {"interview", "offer"}:
                raise ValueError("An offer can only be drafted for an application at interview or offer stage")
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
            cur.execute("select status, application_id from public.offers where id=%s and organization_id=%s for update", [offer_id, organization_id])
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(404, "Offer not found")

            current_status = existing["status"]
            if current_status != "draft" and COMMERCIAL_OFFER_FIELDS.intersection(d):
                raise HTTPException(409, "Offer terms cannot be edited after the offer is sent; create a new offer instead")

            if "status" in d:
                next_status = d["status"]
                if next_status != current_status and next_status not in ALLOWED_OFFER_TRANSITIONS.get(current_status, set()):
                    raise HTTPException(409, "Invalid offer status transition")
                if next_status == "sent" and next_status != current_status:
                    d["sent_at"] = "now()"
                elif next_status in {"accepted", "rejected", "withdrawn", "expired"} and next_status != current_status:
                    d["responded_at"] = "now()"

                if next_status in {"sent", "accepted"} and next_status != current_status:
                    cur.execute(
                        "select status from public.applications where id=%s and organization_id=%s for update",
                        [existing["application_id"], organization_id],
                    )
                    application = cur.fetchone()
                    if application is None:
                        raise HTTPException(409, "Offer application no longer exists")
                    application_status = application["status"]
                    if next_status == "sent":
                        if application_status not in {"interview", "offer"}:
                            raise HTTPException(409, "Application must be at interview or offer stage before sending an offer")
                        if application_status == "interview":
                            cur.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                            cur.execute(
                                "update public.applications set status='offer',updated_at=now() where id=%s and organization_id=%s",
                                [existing["application_id"], organization_id],
                            )
                    elif application_status != "offer":
                        raise HTTPException(409, "Application must be at offer stage before accepting an offer")
                    else:
                        cur.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                        cur.execute(
                            "update public.applications set status='hired',updated_at=now() where id=%s and organization_id=%s",
                            [existing["application_id"], organization_id],
                        )

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
