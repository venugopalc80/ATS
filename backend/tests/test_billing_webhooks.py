import unittest
from unittest.mock import AsyncMock, patch

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


if __name__ == "__main__":
    unittest.main()
