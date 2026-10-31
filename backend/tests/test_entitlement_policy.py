import unittest

from app.services.entitlement_policy import (
    EntitlementDenied,
    feature_enabled,
    require_capacity,
    require_feature,
)


class EntitlementPolicyTests(unittest.TestCase):
    def test_feature_requires_explicit_true(self):
        self.assertTrue(feature_enabled({"ai_assistant": True}, "ai_assistant"))
        self.assertFalse(feature_enabled({}, "ai_assistant"))
        self.assertFalse(feature_enabled({"ai_assistant": 1}, "ai_assistant"))
        with self.assertRaises(EntitlementDenied):
            require_feature({}, "ai_assistant")

    def test_quota_allows_capacity_but_rejects_over_limit(self):
        require_capacity({"seats": 5}, "seats", current_usage=4)
        with self.assertRaises(EntitlementDenied) as raised:
            require_capacity({"seats": 5}, "seats", current_usage=5)
        self.assertEqual(raised.exception.reason, "quota_exceeded")

    def test_explicit_none_means_unlimited(self):
        require_capacity({"seats": None}, "seats", current_usage=100000)

    def test_missing_or_invalid_quota_fails_closed(self):
        for entitlements in ({}, {"seats": True}, {"seats": -1}, {"seats": "5"}):
            with self.subTest(entitlements=entitlements):
                with self.assertRaises(EntitlementDenied):
                    require_capacity(entitlements, "seats", current_usage=0)

    def test_invalid_usage_is_rejected(self):
        with self.assertRaises(ValueError):
            require_capacity({"seats": 5}, "seats", current_usage=-1)
        with self.assertRaises(ValueError):
            require_capacity({"seats": 5}, "seats", current_usage=0, increment=0)


if __name__ == "__main__":
    unittest.main()
