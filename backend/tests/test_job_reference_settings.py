import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers import me as me_router

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")


class JobReferencePrefixTests(unittest.TestCase):
    def test_derives_three_character_prefix_from_organisation_name(self):
        self.assertEqual(me_router.derive_job_reference_prefix("AQERITH"), "AQE")

    def test_derives_prefix_without_spaces_or_punctuation(self):
        self.assertEqual(me_router.derive_job_reference_prefix("North Star Recruitment"), "NOR")

    def test_uses_safe_fallback_for_names_without_two_leading_letters(self):
        self.assertEqual(me_router.derive_job_reference_prefix("7"), "JOB")
        self.assertEqual(me_router.derive_job_reference_prefix("A"), "JOB")

    def test_prefix_is_normalised_to_uppercase(self):
        self.assertEqual(me_router.JobReferenceSettingsUpdate(prefix="aqe").prefix, "AQE")

    def test_rejects_invalid_prefix(self):
        for prefix in ("A", "A-B", "1AQ", "TOO-LONG99", " "):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                me_router.JobReferenceSettingsUpdate(prefix=prefix)


class JobReferenceSettingsEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_cannot_read_reference_settings(self):
        with patch.object(me_router, "assert_org_admin", side_effect=HTTPException(403, "Admin access required")):
            with self.assertRaises(HTTPException) as raised:
                await me_router.get_job_reference_settings(ORG, USER)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_non_admin_cannot_change_reference_settings(self):
        payload = me_router.JobReferenceSettingsUpdate(prefix="AQE")
        with patch.object(me_router, "assert_org_admin", side_effect=HTTPException(403, "Admin access required")):
            with self.assertRaises(HTTPException) as raised:
                await me_router.update_job_reference_settings(ORG, payload, USER)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_update_changes_prefix_and_keeps_existing_counter_floor(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"job_reference_prefix": "AQE", "job_reference_next_number": 14}
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False

        with patch.object(me_router, "assert_org_admin"), patch.object(me_router, "get_connection", return_value=connection):
            result = await me_router.update_job_reference_settings(
                ORG, me_router.JobReferenceSettingsUpdate(prefix="aqe"), USER
            )

        self.assertEqual(result, {"prefix": "AQE", "next_number": 14, "preview": "AQE-014"})
        sql = cursor.execute.call_args.args[0].lower()
        self.assertIn("job_reference_next_number", sql)
        self.assertIn("greatest(", sql)
        self.assertIn("public.jobs", sql)
        self.assertNotIn("update public.jobs", sql)
