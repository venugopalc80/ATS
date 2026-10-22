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
    def __init__(self, subscription=None, entitlements=None):
        self.subscription = subscription
        self.entitlements = entitlements or []
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


if __name__ == "__main__":
    unittest.main()
