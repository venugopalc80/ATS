from uuid import UUID
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import assert_org_admin, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    organization_id: UUID
    plan_id: UUID
    idempotency_key: UUID


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
    """Return subscription details to organisation admins only."""
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


@router.post("/checkout")
async def create_checkout_session(
    payload: CheckoutRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Create a subscription Checkout Session using server-owned Stripe price IDs."""
    assert_org_admin(user_id, payload.organization_id)
    secret_key = os.getenv("STRIPE_SECRET_KEY")
    frontend_url = os.getenv("FRONTEND_URL", "https://aqerith.com").rstrip("/")
    if not secret_key:
        raise HTTPException(status_code=503, detail="Subscription checkout is not configured")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id, plan_key, display_name from public.subscription_plans where id=%s and is_active=true",
                    [payload.plan_id],
                )
                plan = cursor.fetchone()
                if plan is None:
                    raise HTTPException(status_code=404, detail="Active plan not found")
                cursor.execute(
                    """
                    select status from public.organization_subscriptions
                    where organization_id=%s
                      and status in ('incomplete','trialing','active','past_due','paused','unpaid')
                    limit 1
                    """,
                    [payload.organization_id],
                )
                existing = cursor.fetchone()
                if existing is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="An existing subscription requires management before starting checkout",
                    )

        price_env_key = "STRIPE_PRICE_ID_" + plan["plan_key"].upper().replace("-", "_")
        price_id = os.getenv(price_env_key)
        if not price_id:
            raise HTTPException(status_code=503, detail="Pricing is not configured for this plan")

        metadata = {
            "organization_id": str(payload.organization_id),
            "plan_id": str(payload.plan_id),
        }
        # Stripe deduplicates retried requests using this stable attempt key. The
        # browser reuses it after network failures/reloads; a cancelled attempt
        # gets a fresh key before the user retries.
        stripe_idempotency_key = (
            f"aqerith-checkout-{payload.organization_id}-{payload.plan_id}-{payload.idempotency_key}"
        )
        session = stripe.checkout.Session.create(
            api_key=secret_key,
            idempotency_key=stripe_idempotency_key,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{frontend_url}/billing?checkout=success",
            cancel_url=f"{frontend_url}/billing?checkout=cancelled",
            client_reference_id=str(payload.organization_id),
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Billing service is unavailable") from exc
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail="Unable to create checkout session") from exc
