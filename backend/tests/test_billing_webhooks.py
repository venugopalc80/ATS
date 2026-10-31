import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import billing_webhooks


class FakeRequest:
    def __init__(self, body=b"{}"):
        self.body = AsyncMock(return_value=body)


class BillingWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_webhook_secret_fails_closed(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                await billing_webhooks.stripe_webhook(FakeRequest(), "sig")
        self.assertEqual(raised.exception.status_code, 503)

    async def test_missing_signature_is_rejected(self):
        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                await billing_webhooks.stripe_webhook(FakeRequest(), None)
        self.assertEqual(raised.exception.status_code, 400)

    async def test_invalid_signature_is_rejected(self):
        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}, clear=False), patch.object(
            billing_webhooks.stripe.Webhook,
            "construct_event",
            side_effect=ValueError("invalid signature"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await billing_webhooks.stripe_webhook(FakeRequest(), "bad-signature")
        self.assertEqual(raised.exception.status_code, 400)

    def test_older_subscription_event_is_ignored(self):
        self.assertFalse(billing_webhooks.should_apply_subscription_event(200, 199))

    def test_newer_or_equal_subscription_event_is_applied(self):
        self.assertTrue(billing_webhooks.should_apply_subscription_event(200, 200))
        self.assertTrue(billing_webhooks.should_apply_subscription_event(200, 201))
        self.assertTrue(billing_webhooks.should_apply_subscription_event(None, 1))

    def test_deleted_subscription_cannot_remain_active(self):
        self.assertEqual(
            billing_webhooks._normalise_status("active", "customer.subscription.deleted"),
            "canceled",
        )

    def test_unknown_provider_status_fails_closed(self):
        self.assertEqual(
            billing_webhooks._normalise_status("unknown_future_status", "customer.subscription.updated"),
            "unpaid",
        )

    async def test_stale_event_is_acknowledged_without_mutating_subscription(self):
        org_id = UUID("11111111-1111-4111-8111-111111111111")
        plan_id = UUID("33333333-3333-4333-8333-333333333333")
        subscription_id = UUID("44444444-4444-4444-8444-444444444444")

        class Cursor:
            def __init__(self):
                self.sql = ""
                self.responses = [
                    {"id": UUID("55555555-5555-4555-8555-555555555555")},  # receipt
                    {"id": org_id},  # organisation exists
                    {"id": plan_id},  # plan exists
                    {
                        "id": subscription_id,
                        "organization_id": org_id,
                        "plan_id": plan_id,
                        "status": "active",
                        "provider_event_created_at": 200,
                    },
                ]
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                self.sql = " ".join(sql.split())
                self.executed.append((self.sql, params))

            def fetchone(self):
                return self.responses.pop(0) if self.responses else None

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        @contextmanager
        def fake_connection():
            with Connection() as connection:
                yield connection

        event = {
            "id": "evt_stale_123",
            "type": "customer.subscription.updated",
            "created": 199,
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "metadata": {
                        "organization_id": str(org_id),
                        "plan_id": str(plan_id),
                    },
                    "status": "past_due",
                    "customer": "cus_test_123",
                }
            },
        }

        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}), patch.object(
            billing_webhooks.stripe.Webhook, "construct_event", return_value=event
        ), patch.object(billing_webhooks, "get_connection", fake_connection):
            result = await billing_webhooks.stripe_webhook(FakeRequest(b'{"test":true}'), "sig_test")

        self.assertEqual(result, {"received": True, "processed": False, "stale": True})
        self.assertTrue(any("failure_code='stale_provider_event'" in sql for sql, _ in cursor.executed))
        self.assertFalse(any("update public.organization_subscriptions" in sql for sql, _ in cursor.executed))


    async def test_stale_event_with_wrong_tenant_metadata_is_rejected(self):
        stored_org_id = UUID("11111111-1111-4111-8111-111111111111")
        incoming_org_id = UUID("22222222-2222-4222-8222-222222222222")
        plan_id = UUID("33333333-3333-4333-8333-333333333333")
        subscription_id = UUID("44444444-4444-4444-8444-444444444444")

        class Cursor:
            def __init__(self):
                self.responses = [
                    {"id": UUID("55555555-5555-4555-8555-555555555555")},
                    {"id": incoming_org_id},
                    {"id": plan_id},
                    {
                        "id": subscription_id,
                        "organization_id": stored_org_id,
                        "plan_id": plan_id,
                        "status": "active",
                        "provider_event_created_at": 200,
                    },
                ]
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                self.executed.append((" ".join(sql.split()), params))

            def fetchone(self):
                return self.responses.pop(0) if self.responses else None

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        @contextmanager
        def fake_connection():
            with Connection() as connection:
                yield connection

        event = {
            "id": "evt_wrong_tenant_stale_123",
            "type": "customer.subscription.updated",
            "created": 199,
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "metadata": {
                        "organization_id": str(incoming_org_id),
                        "plan_id": str(plan_id),
                    },
                    "status": "past_due",
                    "customer": "cus_test_123",
                }
            },
        }

        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}), patch.object(
            billing_webhooks.stripe.Webhook, "construct_event", return_value=event
        ), patch.object(billing_webhooks, "get_connection", fake_connection):
            with self.assertRaises(HTTPException) as raised:
                await billing_webhooks.stripe_webhook(FakeRequest(b'{"test":true}'), "sig_test")

        self.assertEqual(raised.exception.status_code, 500)
        self.assertFalse(any("update public.organization_subscriptions" in sql for sql, _ in cursor.executed))
        self.assertFalse(any("failure_code='stale_provider_event'" in sql for sql, _ in cursor.executed))


    async def test_duplicate_webhook_delivery_is_acknowledged_without_reprocessing(self):
        class Cursor:
            def __init__(self):
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                self.executed.append((" ".join(sql.split()), params))

            def fetchone(self):
                # ON CONFLICT DO NOTHING RETURNING id yields no row for a duplicate.
                return None

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return cursor

        @contextmanager
        def fake_connection():
            with Connection() as connection:
                yield connection

        event = {
            "id": "evt_duplicate_delivery_123",
            "type": "invoice.payment_succeeded",
            "created": 200,
            "data": {"object": {"id": "in_test_123"}},
        }

        with patch.dict("os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}), patch.object(
            billing_webhooks.stripe.Webhook, "construct_event", return_value=event
        ), patch.object(billing_webhooks, "get_connection", fake_connection):
            result = await billing_webhooks.stripe_webhook(FakeRequest(b'{"duplicate":true}'), "sig_test")

        self.assertEqual(result, {"received": True, "duplicate": True})
        self.assertEqual(len(cursor.executed), 1)
        self.assertIn("on conflict (billing_provider, provider_event_id) do nothing", cursor.executed[0][0])
        self.assertFalse(any("organization_subscriptions" in sql for sql, _ in cursor.executed))


if __name__ == "__main__":
    unittest.main()
