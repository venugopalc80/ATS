import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.candidate_tags import CandidateTagCreate


class CandidateTagSchemaTests(unittest.TestCase):
    def test_trims_tag_name(self):
        payload = CandidateTagCreate(organization_id=uuid4(), name="  Shortlist  ")
        self.assertEqual(payload.name, "Shortlist")

    def test_rejects_blank_name(self):
        with self.assertRaises(ValidationError):
            CandidateTagCreate(organization_id=uuid4(), name="   ")

    def test_rejects_name_longer_than_fifty_characters(self):
        with self.assertRaises(ValidationError):
            CandidateTagCreate(organization_id=uuid4(), name="x" * 51)

    def test_rejects_invalid_colour(self):
        with self.assertRaises(ValidationError):
            CandidateTagCreate(organization_id=uuid4(), name="Shortlist", colour="blue")

    def test_accepts_hex_colour(self):
        payload = CandidateTagCreate(organization_id=uuid4(), name="Shortlist", colour="#12aBcF")
        self.assertEqual(payload.colour, "#12aBcF")


if __name__ == "__main__":
    unittest.main()
