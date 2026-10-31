import unittest
from pydantic import ValidationError

from app.routers.organization_settings import OrganizationSettings, OrganizationSettingsPatch


class OrganizationSettingsValidationTests(unittest.TestCase):
    def test_safe_defaults_are_available(self):
        settings = OrganizationSettings()
        self.assertEqual(settings.default_country_code, "GB")
        self.assertEqual(settings.default_currency, "GBP")
        self.assertEqual(settings.timezone, "UTC")

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(ValidationError):
            OrganizationSettings(timezone="Not/A-Timezone")

    def test_country_and_currency_must_be_uppercase_iso_shaped_codes(self):
        with self.assertRaises(ValidationError):
            OrganizationSettings(default_country_code="gb")
        with self.assertRaises(ValidationError):
            OrganizationSettings(default_currency="gbp")

    def test_patch_only_includes_explicit_fields(self):
        patch = OrganizationSettingsPatch(default_currency="USD")
        self.assertEqual(patch.model_dump(exclude_unset=True), {"default_currency": "USD"})

    def test_unknown_settings_are_rejected(self):
        with self.assertRaises(ValidationError):
            OrganizationSettings.model_validate({"unexpected_flag": True})


if __name__ == "__main__":
    unittest.main()
