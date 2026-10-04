from uuid import UUID
from fastapi import HTTPException
from app.db import get_connection
from app.schemas.placements import PlacementCreate, PlacementUpdate
def list_placements(organization_id: UUID,status: str|None=None):
    with get_connection() as c:
        with c.cursor() as cur:
            q="select * from public.placements where organization_id=%s"
            args=[organization_id]
            if status: q+=" and status=%s"; args.append(status)
            q+=" order by start_date desc"; cur.execute(q,args); return cur.fetchall()
def create_placement(payload: PlacementCreate,user_id: UUID):
    d=payload.model_dump(); d["created_by"]=user_id
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("""insert into public.placements (organization_id,application_id,offer_id,job_id,candidate_id,client_id,status,start_date,end_date,fee_amount,fee_currency,fee_type,fee_percentage,notes,created_by)
            values (%(organization_id)s,%(application_id)s,%(offer_id)s,%(job_id)s,%(candidate_id)s,%(client_id)s,%(status)s,%(start_date)s,%(end_date)s,%(fee_amount)s,%(fee_currency)s,%(fee_type)s,%(fee_percentage)s,%(notes)s,%(created_by)s) returning *""",d)
            row=cur.fetchone()
        c.commit(); return row
def get_placement(organization_id: UUID,placement_id: UUID):
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute("select * from public.placements where id=%s and organization_id=%s",[placement_id,organization_id]); row=cur.fetchone()
            if not row: raise HTTPException(404,"Placement not found")
            return row
def update_placement(organization_id: UUID,placement_id: UUID,payload: PlacementUpdate):
    d={k:v for k,v in payload.model_dump().items() if v is not None}
    if not d: return get_placement(organization_id,placement_id)
    sets=", ".join(f"{k}=%({k})s" for k in d); d.update({"placement_id":placement_id,"organization_id":organization_id})
    with get_connection() as c:
        with c.cursor() as cur:
            cur.execute(f"update public.placements set {sets},updated_at=now() where id=%(placement_id)s and organization_id=%(organization_id)s returning *",d); row=cur.fetchone()
            if not row: raise HTTPException(404,"Placement not found")
        c.commit(); return row
