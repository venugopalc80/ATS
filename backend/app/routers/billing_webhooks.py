"""Stripe webhook receiver with signature verification and idempotent processing."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = logging.getLogger(__name__)

STRIPE_SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
}

HISTORY_EVENT_TYPES = {
    "customer.subscription.created": "created",
    "customer.subscription.updated": "reconciled",
    "customer.subscription.deleted": "canceled",
    "customer.subscription.paused": "paused",
    "customer.subscription.resumed": "resumed",
}


def _from_epoch(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def subscription_event_rejection_reason(stored_created: int | None, incoming_created: int) -> str | None:
    """Reject older events and equal-second events whose true order cannot be established."""
    if stored_created is None or incoming_created > stored_created:
        return None
    if incoming_created == stored_created:
        return "ambiguous_provider_event_timestamp"
    return "stale_provider_event"


def should_apply_subscription_event(stored_created: int | None, incoming_created: int) -> bool:
    """Apply only events with a strictly newer provider timestamp."""
    return subscription_event_rejection_reason(stored_created, incoming_created) is None


def _normalise_status(status: str, event_type: str) -> str:
    if event_type == "customer.subscription.deleted":
        return "canceled"
    if status in {"incomplete", "trialing", "active", "past_due", "paused", "canceled", "unpaid"}:
        return status
    if status == "incomplete_expired":
        return "canceled"
    return "unpaid"


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Billing webhook is not configured")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature") from exc

    event_id = str(event["id"])
    event_type = str(event["type"])
    event_created = int(event.get("created") or 0)
    payload_hash = hashlib.sha256(payload).hexdigest()
    data_object = event.get("data", {}).get("object", {})

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.billing_webhook_events
                      (billing_provider, provider_event_id, event_type, payload_sha256, processing_status)
                    values ('stripe', %s, %s, %s, 'processing')
                    on conflict (billing_provider, provider_event_id) do nothing
                    returning id
                    """,
                    [event_id, event_type, payload_hash],
                )
                receipt = cursor.fetchone()
                if receipt is None:
                    return {"received": True, "duplicate": True}

                if event_type in STRIPE_SUBSCRIPTION_EVENTS:
                    metadata = data_object.get("metadata") or {}
                    try:
                        organization_id = UUID(str(metadata.get("organization_id")))
                        plan_id = UUID(str(metadata.get("plan_id")))
                    except (ValueError, TypeError, AttributeError):
                        cursor.execute(
                            """update public.billing_webhook_events
                               set processing_status='ignored', processed_at=now(),
                                   failure_code='missing_subscription_metadata'
                               where id=%s""",
                            [receipt["id"]],
                        )
                        return {"received": True, "ignored": True}

                    provider_subscription_id = str(data_object.get("id") or "")
                    if not provider_subscription_id:
                        raise ValueError("Verified Stripe subscription event has no subscription id")

                    cursor.execute("select id from public.organizations where id=%s", [organization_id])
                    if cursor.fetchone() is None:
                        cursor.execute(
                            """update public.billing_webhook_events
                               set processing_status='ignored', processed_at=now(),
                                   failure_code='unknown_organization'
                               where id=%s""",
                            [receipt["id"]],
                        )
                        return {"received": True, "ignored": True}

                    cursor.execute("select id from public.subscription_plans where id=%s", [plan_id])
                    if cursor.fetchone() is None:
                        cursor.execute(
                            """update public.billing_webhook_events
                               set processing_status='ignored', processed_at=now(),
                                   failure_code='unknown_plan'
                               where id=%s""",
                            [receipt["id"]],
                        )
                        return {"received": True, "ignored": True}

                    customer = data_object.get("customer")
                    if isinstance(customer, dict):
                        customer = customer.get("id")
                    status = _normalise_status(str(data_object.get("status") or "unpaid"), event_type)
                    period_start = _from_epoch(data_object.get("current_period_start"))
                    period_end = _from_epoch(data_object.get("current_period_end"))
                    trial_end = _from_epoch(data_object.get("trial_end"))
                    canceled_at = _from_epoch(data_object.get("canceled_at"))
                    cancel_at_period_end = bool(data_object.get("cancel_at_period_end", False))

                    cursor.execute(
                        """select id, organization_id, plan_id, status, provider_event_created_at
                           from public.organization_subscriptions
                           where billing_provider='stripe' and provider_subscription_id=%s
                           for update""",
                        [provider_subscription_id],
                    )
                    existing = cursor.fetchone()
                    if existing:
                        # Validate tenant binding before stale-event handling; provider IDs
                        # must never be accepted under another organisation's metadata.
                        if str(existing["organization_id"]) != str(organization_id):
                            raise ValueError("Stripe subscription tenant metadata does not match stored tenant")
                        rejection_reason = subscription_event_rejection_reason(
                            existing.get("provider_event_created_at"), event_created
                        )
                        if rejection_reason:
                            cursor.execute(
                                """update public.billing_webhook_events
                                   set organization_id=%s, processing_status='ignored',
                                       processed_at=now(), failure_code=%s
                                   where id=%s""",
                                [organization_id, rejection_reason, receipt["id"]],
                            )
                            result = {"received": True, "processed": False}
                            result["ambiguous" if rejection_reason == "ambiguous_provider_event_timestamp" else "stale"] = True
                            return result

                    previous_state = {}
                    if existing:
                        previous_state = {
                            "organization_id": str(existing["organization_id"]),
                            "plan_id": str(existing["plan_id"]),
                            "status": existing["status"],
                        }
                        cursor.execute(
                            """update public.organization_subscriptions
                               set plan_id=%s, status=%s, provider_customer_id=%s,
                                   current_period_start=%s, current_period_end=%s,
                                   trial_ends_at=%s, cancel_at_period_end=%s,
                                   canceled_at=%s, provider_event_created_at=%s, updated_at=now()
                               where id=%s returning id""",
                            [plan_id, status, customer, period_start, period_end, trial_end,
                             cancel_at_period_end, canceled_at, event_created, existing["id"]],
                        )
                        subscription_id = cursor.fetchone()["id"]
                    else:
                        cursor.execute(
                            """insert into public.organization_subscriptions
                               (organization_id, plan_id, status, billing_provider,
                                provider_customer_id, provider_subscription_id,
                                current_period_start, current_period_end, trial_ends_at,
                                cancel_at_period_end, canceled_at, provider_event_created_at)
                               values (%s, %s, %s, 'stripe', %s, %s, %s, %s, %s, %s, %s, %s)
                               returning id""",
                            [organization_id, plan_id, status, customer, provider_subscription_id,
                             period_start, period_end, trial_end, cancel_at_period_end, canceled_at,
                             event_created],
                        )
                        subscription_id = cursor.fetchone()["id"]

                    cursor.execute(
                        """insert into public.organization_subscription_history
                           (organization_id, subscription_id, event_type, previous_state,
                            new_state, source)
                           values (%s, %s, %s, %s::jsonb, %s::jsonb, 'provider_webhook')""",
                        [
                            organization_id, subscription_id, HISTORY_EVENT_TYPES[event_type],
                            json.dumps(previous_state),
                            json.dumps({
                                "plan_id": str(plan_id),
                                "status": status,
                                "provider_subscription_id": provider_subscription_id,
                            }),
                        ],
                    )
                    cursor.execute(
                        "update public.billing_webhook_events set organization_id=%s where id=%s",
                        [organization_id, receipt["id"]],
                    )

                cursor.execute(
                    """update public.billing_webhook_events
                       set processing_status='processed', processed_at=now()
                       where id=%s""",
                    [receipt["id"]],
                )
        return {"received": True, "processed": event_type in STRIPE_SUBSCRIPTION_EVENTS}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Billing webhook processing is unavailable") from exc
    except Exception as exc:
        logger.exception("Stripe webhook processing failed for event id %s", event_id)
        raise HTTPException(status_code=500, detail="Billing webhook processing failed") from exc
