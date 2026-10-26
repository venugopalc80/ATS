import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from app.routers import billing as billing_router


ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
PLAN = UUID("33333333-3333-4333-8333-333333333333")


class FakeCursor:
    def __init__(self, subscription=None, entitlements=None, plan=None):
        self.subscription = subscription
        self.entitlements = entitlements or []
        self.plan = plan
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())

    def fetchone(self):
        if "from public.organization_subscriptions" in self.sql:
            return self.subscription
        if "from public.subscription_plans" in self.sql:
            return self.plan
        return None

    def fetchall(self):
        if "from public.plan_entitlements" in self.sql:
            return self.entitlements
        return []


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class BillingEndpointTests(unittest.IsolatedAsyncioTestCase):
    def connection_factory(self, cursor):
        @contextmanager
        def fake_connection():
            with FakeConnection(cursor) as connection:
                yield connection
        return fake_connection

    async def test_missing_subscription_returns_empty_entitlements(self):
        cursor = FakeCursor(subscription=None)
        with patch.object(billing_router, "assert_org_admin") as admin, patch.object(
            billing_router, "get_connection", self.connection_factory(cursor)
        ):
            result = await billing_router.get_subscription(organization_id=ORG, user_id=USER)
        admin.assert_called_once_with(USER, ORG)
        self.assertIsNone(result["subscription"])
        self.assertEqual(result["entitlements"], {})

    async def test_active_subscription_returns_plan_entitlements(self):
        cursor = FakeCursor(
            subscription={
                "id": UUID("44444444-4444-4444-8444-444444444444"),
                "organization_id": ORG,
                "status": "active",
                "plan_id": PLAN,
                "plan_key": "starter",
            },
            entitlements=[
                {"entitlement_key": "seats", "entitlement_value": 5},
                {"entitlement_key": "ai_assistant", "entitlement_value": True},
            ],
        )
        with patch.object(billing_router, "assert_org_admin"), patch.object(
            billing_router, "get_connection", self.connection_factory(cursor)
        ):
            result = await billing_router.get_subscription(organization_id=ORG, user_id=USER)
        self.assertEqual(result["entitlements"], {"seats": 5, "ai_assistant": True})

    async def test_past_due_subscription_fails_closed(self):
        cursor = FakeCursor(
            subscription={
                "id": UUID("44444444-4444-4444-8444-444444444444"),
                "organization_id": ORG,
                "status": "past_due",
                "plan_id": PLAN,
                "plan_key": "starter",
            },
        )
        with patch.object(billing_router, "assert_org_admin"), patch.object(
            billing_router, "get_connection", self.connection_factory(cursor)
        ):
            result = await billing_router.get_subscription(organization_id=ORG, user_id=USER)
        self.assertEqual(result["entitlements"], {})

    async def test_checkout_passes_stable_idempotency_key_to_stripe(self):
        plan = {"id": PLAN, "plan_key": "starter", "display_name": "Starter"}
        cursor = FakeCursor(subscription=None, plan=plan)
        attempt_key = UUID("55555555-5555-4555-8555-555555555555")
        expected_key = "aqerith-checkout-" + str(ORG) + "-" + str(PLAN) + "-" + str(attempt_key)
        with patch.object(billing_router, "assert_org_admin"), patch.object(
            billing_router, "get_connection", self.connection_factory(cursor)
        ), patch.dict("os.environ", {
            "STRIPE_SECRET_KEY": "sk_test_placeholder",
            "STRIPE_PRICE_ID_STARTER": "price_test_placeholder",
            "FRONTEND_URL": "https://aqerith.com",
        }), patch.object(
            billing_router.stripe.checkout.Session,
            "create",
            return_value=type("Session", (), {"url": "https://checkout.stripe.test/session", "id": "cs_test_123"})(),
        ) as stripe_create:
            payload = billing_router.CheckoutRequest(
                organization_id=ORG, plan_id=PLAN, idempotency_key=attempt_key
            )
            result = await billing_router.create_checkout_session(payload=payload, user_id=USER)

        self.assertEqual(result["session_id"], "cs_test_123")
        self.assertEqual(result["checkout_url"], "https://checkout.stripe.test/session")
        self.assertEqual(stripe_create.call_args.kwargs["idempotency_key"], expected_key)


if __name__ == "__main__":
    unittest.main()
