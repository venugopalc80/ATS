from uuid import UUID

from fastapi import HTTPException

from app.db import get_connection
from app.schemas.offers import OfferCreate, OfferUpdate
from app.services.offer_management_service import _save_version


TERM_FIELDS = {
    "title", "employment_type", "start_date", "salary_amount", "salary_currency",
    "bonus_amount", "benefits", "expires_at", "notes",
}


def list_offers(organization_id: UUID, status: str | None = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "select * from public.offers where organization_id=%s and status=%s order by created_at desc",
                    [organization_id, status],
                )
            else:
                cur.execute(
                    "select * from public.offers where organization_id=%s order by created_at desc",
                    [organization_id],
                )
            return cur.fetchall()


def create_offer(payload: OfferCreate, user_id: UUID):
    data = payload.model_dump()
    data["created_by"] = user_id
    # Approval and issuance are dedicated actions; clients cannot create an already-issued offer.
    data["status"] = "draft"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from public.applications where id=%s and organization_id=%s",
                [payload.application_id, payload.organization_id],
            )
            if cur.fetchone() is None:
                raise ValueError("Application must belong to the same organization")
            cur.execute(
                """insert into public.offers
                (organization_id,application_id,title,status,employment_type,start_date,salary_amount,
                 salary_currency,bonus_amount,benefits,expires_at,notes,created_by,current_version)
                values (%(organization_id)s,%(application_id)s,%(title)s,'draft',%(employment_type)s,
                 %(start_date)s,%(salary_amount)s,%(salary_currency)s,%(bonus_amount)s,%(benefits)s,
                 %(expires_at)s,%(notes)s,%(created_by)s,1)
                returning *""",
                data,
            )
            row = cur.fetchone()
            _save_version(cur, payload.organization_id, row["id"], row, user_id, 1)
        conn.commit()
        return row


def get_offer(organization_id: UUID, offer_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s",
                [offer_id, organization_id],
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(404, "Offer not found")
            return row


def update_offer(organization_id: UUID, offer_id: UUID, payload: OfferUpdate, actor_user_id: UUID):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_offer(organization_id, offer_id)
    if "status" in data:
        raise HTTPException(422, "Use the dedicated offer lifecycle action to change status")
    if set(data) - TERM_FIELDS:
        raise HTTPException(422, "Unsupported offer fields")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s for update",
                [offer_id, organization_id],
            )
            existing = cur.fetchone()
            if existing is None:
                raise HTTPException(404, "Offer not found")
            if existing["status"] != "draft":
                raise HTTPException(409, "Only draft offer terms can be edited; create a new version after returning to draft")
            assignments = [f"{key}=%({key})s" for key in data]
            values = {**data, "offer_id": offer_id, "organization_id": organization_id}
            next_version = (existing.get("current_version") or 1) + 1
            cur.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
            cur.execute(
                f"""update public.offers set {', '.join(assignments)}, current_version=%(version)s,
                    updated_at=now() where id=%(offer_id)s and organization_id=%(organization_id)s
                    returning *""",
                {**values, "version": next_version},
            )
            row = cur.fetchone()
            _save_version(cur, organization_id, offer_id, row, actor_user_id, next_version)
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'offer_terms_version_created','offer',%s,%s::jsonb)""",
                [organization_id, actor_user_id, offer_id,
                 __import__("json").dumps({"version": next_version})],
            )
        conn.commit()
        return row
