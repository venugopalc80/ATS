from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router=APIRouter(prefix="/api/dashboard",tags=["dashboard"])

@router.get("")
async def dashboard(organization_id: UUID, user_id: UUID=Depends(get_current_user_id)):
    assert_org_member(user_id,organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) as total from public.jobs where organization_id=%s and status='open'",[organization_id])
                open_jobs=cursor.fetchone()["total"]
                cursor.execute("select count(*) as total from public.candidates where organization_id=%s and status='active'",[organization_id])
                active_candidates=cursor.fetchone()["total"]
                cursor.execute("select count(*) as total from public.clients where organization_id=%s and status='active'",[organization_id])
                active_clients=cursor.fetchone()["total"]
                cursor.execute("select status,count(*) as total from public.applications where organization_id=%s group by status", [organization_id])
                pipeline={r["status"]:r["total"] for r in cursor.fetchall()}
                cursor.execute("""select j.id,j.title,coalesce(c.name,'Direct client') as client,j.status,count(a.id)::int as applicants from public.jobs j left join public.clients c on c.id=j.client_id left join public.applications a on a.job_id=j.id where j.organization_id=%s and j.status in ('open','on_hold') group by j.id,j.title,c.name,j.status order by j.created_at desc limit 6""",[organization_id])
                jobs=list(cursor.fetchall())
                cursor.execute("select action,entity_type,entity_id,metadata,created_at from public.audit_events where organization_id=%s order by created_at desc limit 8",[organization_id])
                activity=list(cursor.fetchall())
        return {"open_requisitions":open_jobs,"active_candidates":active_candidates,"active_clients":active_clients,"pipeline":pipeline,"jobs":jobs,"activity":activity}
    except (DatabaseConfigurationError,DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503,detail="Database operation failed") from exc
