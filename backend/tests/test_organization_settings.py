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
        patch = OrganizationSettingsPatch(default_currency="USD", expected_version=3)
        self.assertEqual(
            patch.model_dump(exclude_unset=True, exclude={"expected_version"}),
            {"default_currency": "USD"},
        )
        self.assertEqual(patch.expected_version, 3)

    def test_unknown_settings_are_rejected(self):
        with self.assertRaises(ValidationError):
            OrganizationSettings.model_validate({"unexpected_flag": True})


class OrganizationSettingsConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_expected_version_is_rejected_without_writing(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from uuid import UUID
        from fastapi import HTTPException
        from app.routers import organization_settings

        organization_id = UUID("11111111-1111-4111-8111-111111111111")
        user_id = UUID("99999999-9999-4999-8999-999999999999")

        class Cursor:
            def __init__(self):
                self.responses = [
                    {"id": organization_id},
                    {"version": 5, "settings": OrganizationSettings().model_dump()},
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

        payload = organization_settings.OrganizationSettingsPatch(
            default_currency="USD",
            expected_version=4,
        )
        with patch.object(organization_settings, "assert_org_admin"), patch.object(
            organization_settings, "get_connection", fake_connection
        ):
            with self.assertRaises(HTTPException) as raised:
                await organization_settings.update_organization_settings(
                    organization_id, payload, user_id=user_id
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("current version 5", raised.exception.detail)
        self.assertEqual(len(cursor.executed), 2)
        self.assertFalse(any("insert into public.organization_settings_versions" in sql.lower() for sql, _ in cursor.executed))
        self.assertFalse(any("insert into public.audit_events" in sql.lower() for sql, _ in cursor.executed))


if __name__ == "__main__":
    unittest.main()
