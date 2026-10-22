from typing import Any
from uuid import UUID
from psycopg.types.json import Jsonb
from app.db import get_connection
from app.schemas.requisitions import RequisitionCreate, RequisitionUpdate

COLUMNS = """
 id, organization_id, requisition_code, title, department, client_id, requested_by,
 hiring_manager_id, recruiter_id, headcount, justification, budget_min, budget_max,
 location, country_code, employment_type, work_mode, salary_min, salary_max,
 salary_currency, required_skills, target_start_date, target_close_date, status,
 submitted_at, approved_by, approved_at, rejected_by, rejected_at, rejection_reason,
 approval_comment, job_id, created_at, updated_at
"""

def audit(cursor, org_id: UUID, actor_id: UUID, action: str, entity_id: UUID, metadata: dict[str, Any] | None = None):
    cursor.execute(
        "insert into public.audit_events (organization_id,actor_user_id,action,entity_type,entity_id,metadata) values (%s,%s,%s,'job_requisition',%s,%s)",
        [org_id, actor_id, action, entity_id, Jsonb(metadata or {})],
    )

class RequisitionService:
    async def list_requisitions(self, organization_id: UUID, status: str | None, search: str | None, limit: int, offset: int):
        query = f"select {COLUMNS} from public.job_requisitions where organization_id=%s"
        params: list[Any] = [organization_id]
        if status:
            query += " and status=%s"
            params.append(status)
        if search:
            query += " and (title ilike %s or requisition_code ilike %s or department ilike %s)"
            pattern = "%" + search + "%"
            params.extend([pattern, pattern, pattern])
        query += " order by updated_at desc, created_at desc limit %s offset %s"
        params.extend([limit, offset])
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def get_requisition(self, requisition_id: UUID):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select {COLUMNS} from public.job_requisitions where id=%s", [requisition_id])
                return cursor.fetchone()

    async def create_requisition(self, payload: RequisitionCreate, user_id: UUID):
        data = payload.model_dump(mode="python", exclude={"organization_id"})
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 'REQ-' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,8)) as code")
                data.update({"organization_id": payload.organization_id, "requisition_code": cursor.fetchone()["code"], "requested_by": user_id, "status": "draft"})
                columns = list(data)
                cursor.execute(
                    f"insert into public.job_requisitions ({', '.join(columns)}) values ({', '.join(['%s']*len(columns))}) returning {COLUMNS}",
                    [data[c] for c in columns],
                )
                row = cursor.fetchone()
                audit(cursor, payload.organization_id, user_id, "requisition.created", row["id"], {"status": "draft"})
                return row

    async def update_requisition(self, requisition_id: UUID, payload: RequisitionUpdate, actor_id: UUID):
        data = payload.model_dump(mode="python", exclude_unset=True)
        if not data:
            return await self.get_requisition(requisition_id)
        assignments = ", ".join(f"{column}=%s" for column in data)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Lock and read the existing row so audit history captures actual before/after values.
                cursor.execute(
                    f"select {COLUMNS} from public.job_requisitions where id=%s for update",
                    [requisition_id],
                )
                before = cursor.fetchone()
                if before is None:
                    return None
                changes = {
                    key: {"old": str(before.get(key)) if before.get(key) is not None else None,
                          "new": str(value) if value is not None else None}
                    for key, value in data.items()
                    if before.get(key) != value
                }
                cursor.execute(
                    f"update public.job_requisitions set {assignments},updated_at=now() where id=%s returning {COLUMNS}",
                    [*data.values(), requisition_id],
                )
                row = cursor.fetchone()
                if row and changes:
                    audit(cursor, row["organization_id"], actor_id, "requisition.updated", requisition_id,
                          {"changes": changes})
                return row

    async def submit(self, requisition_id: UUID, actor_id: UUID):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"update public.job_requisitions set status='pending_approval',submitted_at=now(),rejected_by=null,rejected_at=null,rejection_reason=null,updated_at=now() where id=%s and status in ('draft','rejected') returning {COLUMNS}",
                    [requisition_id],
                )
                row = cursor.fetchone()
                if row:
                    audit(cursor, row["organization_id"], actor_id, "requisition.submitted", requisition_id, {"status": "pending_approval"})
                return row

    async def decide(self, requisition_id: UUID, actor_id: UUID, approve: bool, comment: str):
        status = "approved" if approve else "rejected"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""update public.job_requisitions set status=%s,
                        approved_by=case when %s then %s else approved_by end,
                        approved_at=case when %s then now() else approved_at end,
                        approval_comment=%s,
                        rejected_by=case when %s then null else %s end,
                        rejected_at=case when %s then null else now() end,
                        rejection_reason=case when %s then null else %s end, updated_at=now()
                        where id=%s and status='pending_approval' returning {COLUMNS}""",
                    [status, approve, actor_id, approve, comment, approve, actor_id, approve, approve, comment, requisition_id],
                )
                row = cursor.fetchone()
                if row:
                    audit(cursor, row["organization_id"], actor_id, "requisition." + status, requisition_id, {"comment": comment})
                return row

    async def convert_to_job(self, requisition_id: UUID, actor_id: UUID):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select {COLUMNS} from public.job_requisitions where id=%s for update", [requisition_id])
                req = cursor.fetchone()
                if not req:
                    return None
                if req["status"] == "converted" and req["job_id"]:
                    cursor.execute("select id,organization_id,job_code,title,status from public.jobs where id=%s", [req["job_id"]])
                    return {"requisition": req, "job": cursor.fetchone(), "already_converted": True}
                if req["status"] != "approved":
                    raise ValueError("Only an approved requisition can be converted to a job")
                cursor.execute(
                    """insert into public.jobs (organization_id,client_id,job_code,title,description,location,country_code,
                       employment_type,work_mode,salary_min,salary_max,salary_currency,required_skills,recruiter_id,
                       hiring_manager_id,created_by,status)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft')
                       returning id,organization_id,job_code,title,status""",
                    [req["organization_id"], req["client_id"], req["requisition_code"], req["title"], req["justification"],
                     req["location"], req["country_code"], req["employment_type"], req["work_mode"], req["salary_min"],
                     req["salary_max"], req["salary_currency"], req["required_skills"], req["recruiter_id"], req["hiring_manager_id"], actor_id],
                )
                job = cursor.fetchone()
                cursor.execute(f"update public.job_requisitions set status='converted',job_id=%s,updated_at=now() where id=%s returning {COLUMNS}", [job["id"], requisition_id])
                updated = cursor.fetchone()
                audit(cursor, req["organization_id"], actor_id, "requisition.converted", requisition_id, {"job_id": str(job["id"])})
                cursor.execute("insert into public.audit_events (organization_id,actor_user_id,action,entity_type,entity_id,metadata) values (%s,%s,'job.created_from_requisition','job',%s,%s)", [req["organization_id"], actor_id, job["id"], Jsonb({"requisition_id": str(requisition_id)})])
                return {"requisition": updated, "job": job, "already_converted": False}
