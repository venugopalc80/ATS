import unittest
from datetime import datetime, timezone
from uuid import UUID

from pydantic import ValidationError

from app.schemas.candidates import CandidateCreate, CandidateOut, CandidateUpdate


ORG = UUID("11111111-1111-4111-8111-111111111111")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
NOW = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)


class CandidateConsentMetadataContractTests(unittest.TestCase):
    def test_candidate_create_cannot_forge_consent_or_retention_metadata(self):
        payload = {
            "organization_id": ORG,
            "first_name": "Taylor",
            "email": "taylor@example.com",
            "consent_recorded_at": NOW.isoformat(),
            "consent_purpose": "Application for role",
            "retention_until": NOW.isoformat(),
        }
        with self.assertRaises(ValidationError) as error:
            CandidateCreate.model_validate(payload)

        rejected = {item["loc"][0] for item in error.exception.errors()}
        self.assertTrue({"consent_recorded_at", "consent_purpose", "retention_until"}.issubset(rejected))

    def test_candidate_update_cannot_overwrite_consent_or_retention_metadata(self):
        for field, value in (
            ("consent_recorded_at", NOW.isoformat()),
            ("consent_purpose", "Changed purpose"),
            ("retention_until", NOW.isoformat()),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    CandidateUpdate.model_validate({field: value})

    def test_candidate_output_still_exposes_server_recorded_compliance_metadata(self):
        result = CandidateOut.model_validate({
            "id": CANDIDATE,
            "organization_id": ORG,
            "first_name": "Taylor",
            "consent_recorded_at": NOW,
            "consent_purpose": "Application for role",
            "retention_until": NOW,
            "created_at": NOW,
            "updated_at": NOW,
        })
        self.assertEqual(result.consent_recorded_at, NOW)
        self.assertEqual(result.consent_purpose, "Application for role")
        self.assertEqual(result.retention_until, NOW)


if __name__ == "__main__":
    unittest.main()
