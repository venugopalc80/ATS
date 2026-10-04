from uuid import UUID
from fastapi import HTTPException
from app.db import get_connection
from app.schemas.offers import OfferCreate, OfferUpdate
def list_offers(organization_id: UUID,status: str|None=None):
    with get_connection() as c:
        with c.cursor() as cur:
            if status: cur.execute("select * from public.offers where organization_id=%s and status=%s order by created_at desc",[organization_id,status])
            else: cur.execute("select * from public.offers where organization_id=%s order by created_at desc",[organization_id])
            return cur.fetchall()
def create_offer(payload: OfferCreate,user_id: UUID):
    d=payload.model_dump(); d["created_by"]=user_id
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("""insert into public.offers (organization_id,application_id,title,status,employment_type,start_date,salary_amount,salary_currency,bonus_amount,benefits,expires_at,notes,created_by)
            values (%(organization_id)s,%(application_id)s,%(title)s,%(status)s,%(employment_type)s,%(start_date)s,%(salary_amount)s,%(salary_currency)s,%(bonus_amount)s,%(benefits)s,%(expires_at)s,%(notes)s,%(created_by)s) returning *""",d)
            row=cur.fetchone()
        c.commit(); return row
def get_offer(organization_id: UUID,offer_id: UUID):
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select * from public.offers where id=%s and organization_id=%s",[offer_id,organization_id]); row=cur.fetchone()
            if not row: raise HTTPException(404,"Offer not found")
            return row
def update_offer(organization_id: UUID,offer_id: UUID,payload: OfferUpdate):
    d={k:v for k,v in payload.model_dump().items() if v is not None}
    if not d: return get_offer(organization_id,offer_id)
    sets=", ".join(f"{k}=%({k})s" for k in d); d.update({"offer_id":offer_id,"organization_id":organization_id})
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute(f"update public.offers set {sets},updated_at=now() where id=%(offer_id)s and organization_id=%(organization_id)s returning *",d); row=cur.fetchone()
            if not row: raise HTTPException(404,"Offer not found")
        c.commit(); return row
