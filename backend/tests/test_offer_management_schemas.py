import unittest
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.offer_management import OfferApprovalDecision, OfferCandidateResponse
from app.schemas.offers import OfferCreate, OfferUpdate


class OfferManagementSchemaTests(unittest.TestCase):
    def test_offer_creation_defaults_to_draft(self):
        offer = OfferCreate(
            organization_id=uuid4(),
            application_id=uuid4(),
            title="Senior Engineer",
        )
        self.assertEqual(offer.status, "draft")

    def test_approval_decision_rejects_unknown_values(self):
        with self.assertRaises(ValidationError):
            OfferApprovalDecision(decision="issued")

    def test_candidate_response_requires_evidence_reference(self):
        with self.assertRaises(ValidationError):
            OfferCandidateResponse(response="accepted", evidence_reference="   ")

    def test_candidate_response_requires_known_response(self):
        with self.assertRaises(ValidationError):
            OfferCandidateResponse(response="approved", evidence_reference="email-123")

    def test_salary_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            OfferCreate(
                organization_id=uuid4(),
                application_id=uuid4(),
                title="Engineer",
                salary_amount=-1,
            )

    def test_unknown_offer_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            OfferUpdate.model_validate({"unreviewed_field": "value"})

    def test_currency_is_normalized(self):
        offer = OfferCreate(
            organization_id=uuid4(),
            application_id=uuid4(),
            title="Engineer",
            salary_currency="gbp",
        )
        self.assertEqual(offer.salary_currency, "GBP")


if __name__ == "__main__":
    unittest.main()
