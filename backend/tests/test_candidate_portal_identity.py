import unittest
from types import SimpleNamespace

from app.routers.candidate_portal import _verified_email


class CandidatePortalIdentityTests(unittest.TestCase):
    def test_verified_email_is_normalized(self):
        user = SimpleNamespace(email=" Candidate@Example.com ", email_confirmed_at="2026-10-01T10:00:00Z")
        self.assertEqual(_verified_email(user), "candidate@example.com")

    def test_unverified_email_cannot_link(self):
        user = SimpleNamespace(email="candidate@example.com", email_confirmed_at=None, confirmed_at=None)
        self.assertIsNone(_verified_email(user))

    def test_missing_or_malformed_email_cannot_link(self):
        self.assertIsNone(_verified_email(SimpleNamespace(email=None, email_confirmed_at="2026-10-01")))
        self.assertIsNone(_verified_email(SimpleNamespace(email="not-an-email", email_confirmed_at="2026-10-01")))


if __name__ == "__main__":
    unittest.main()
