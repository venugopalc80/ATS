from types import SimpleNamespace

from app.routers.candidate_portal import _verified_email


def test_verified_email_is_normalized():
    user = SimpleNamespace(email=" Candidate@Example.com ", email_confirmed_at="2026-10-01T10:00:00Z")
    assert _verified_email(user) == "candidate@example.com"


def test_unverified_email_cannot_link():
    user = SimpleNamespace(email="candidate@example.com", email_confirmed_at=None, confirmed_at=None)
    assert _verified_email(user) is None


def test_missing_or_malformed_email_cannot_link():
    assert _verified_email(SimpleNamespace(email=None, email_confirmed_at="2026-10-01")) is None
    assert _verified_email(SimpleNamespace(email="not-an-email", email_confirmed_at="2026-10-01")) is None
