from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import assert_org_admin, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans")
async def list_plans(user_id: UUID = Depends(get_current_user_id)):
    """Return the active plan catalogue and its public entitlement definitions."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select p.id, p.plan_key, p.display_name, p.description,
                           coalesce(
                             jsonb_object_agg(e.entitlement_key, e.entitlement_value)
                               filter (where e.entitlement_key is not null),
                             '{}'::jsonb
                           ) as entitlements
                    from public.subscription_plans p
                    left join public.plan_entitlements e on e.plan_id = p.id
                    where p.is_active = true
                    group by p.id
                    order by p.display_name
                    """
                )
                plans = list(cursor.fetchall())
        return {"plans": plans}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Billing service is unavailable") from exc


@router.get("/subscription")
async def get_subscription(
    organization_id: UUID = Query(...),
    user_id: UUID = Depends(get_current_user_id),
):
    """Return subscription details to organisation admins only.

    Entitlements are resolved server-side. Only active and trialing subscriptions
    receive their plan entitlements; all other states fail closed.
    """
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select s.id, s.organization_id, s.status, s.billing_provider,
                           s.current_period_start, s.current_period_end, s.trial_ends_at,
                           s.cancel_at_period_end, s.canceled_at, s.created_at, s.updated_at,
                           p.id as plan_id, p.plan_key, p.display_name as plan_name
                    from public.organization_subscriptions s
                    join public.subscription_plans p on p.id = s.plan_id
                    where s.organization_id = %s
                    order by s.created_at desc
                    limit 1
                    """,
                    [organization_id],
                )
                subscription = cursor.fetchone()
                if subscription is None:
                    return {"subscription": None, "entitlements": {}}

                if subscription["status"] not in {"active", "trialing"}:
                    return {"subscription": subscription, "entitlements": {}}

                cursor.execute(
                    """
                    select e.entitlement_key, e.entitlement_value
                    from public.plan_entitlements e
                    where e.plan_id = %s
                    order by e.entitlement_key
                    """,
                    [subscription["plan_id"]],
                )
                entitlements = {
                    row["entitlement_key"]: row["entitlement_value"]
                    for row in cursor.fetchall()
                }
                return {"subscription": subscription, "entitlements": entitlements}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Billing service is unavailable") from exc
