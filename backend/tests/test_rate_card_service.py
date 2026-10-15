import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from app.schemas.rate_cards import RateCardCreate, RateCardUpdate
from app.services.rate_card_service import RateCardService, _validate_terms


ORG = UUID("11111111-1111-4111-8111-111111111111")
CLIENT = UUID("33333333-3333-4333-8333-333333333333")
ACTOR = UUID("22222222-2222-4222-8222-222222222222")
CARD = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def payload(**overrides):
    data = {
        "organization_id": ORG,
        "client_id": CLIENT,
        "name": "Permanent placement",
        "employment_type": "permanent",
        "rate_basis": "percentage_fee",
        "currency": "GBP",
        "rate_amount": None,
        "fee_percentage": Decimal("15"),
        "effective_from": date(2026, 10, 1),
        "effective_to": None,
        "status": "draft",
        "notes": None,
    }
    data.update(overrides)
    return RateCardCreate(**data)


class FakeCursor:
    def __init__(self, client_exists=True, version=0, existing=None, overlap=None):
        self.sql = ""
        self.params = []
        self.queries = []
        self.client_exists = client_exists
        self.version = version
        self.existing = existing
        self.overlap = overlap
        self.inserted = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.params = params or []
        self.queries.append((self.sql, self.params))
        if self.sql.startswith("insert into public.rate_cards"):
            columns = self.sql.split("(", 1)[1].split(")", 1)[0].split(",")
            self.inserted = dict(zip(columns, self.params))

    def fetchone(self):
        if "from public.clients where id=%s and organization_id=%s" in self.sql:
            return {"id": CLIENT} if self.client_exists else None
        if "select coalesce(max(version)" in self.sql:
            return {"max_version": self.version}
        if self.sql.startswith("insert into public.rate_cards"):
            return {
                "id": CARD, "organization_id": ORG, "client_id": CLIENT, "job_id": None,
                "name": self.inserted["name"], "employment_type": self.inserted["employment_type"],
                "rate_basis": self.inserted["rate_basis"], "currency": self.inserted["currency"],
                "rate_amount": self.inserted["rate_amount"], "fee_percentage": self.inserted["fee_percentage"],
                "effective_from": self.inserted["effective_from"], "effective_to": self.inserted["effective_to"],
                "status": self.inserted["status"], "version": self.inserted["version"],
                "notes": self.inserted["notes"], "created_by": ACTOR, "created_at": NOW, "updated_at": NOW,
            }
        if "for update" in self.sql:
            return self.existing
        if "status='active'" in self.sql and "limit 1" in self.sql:
            return self.overlap
        if self.sql.startswith("update public.rate_cards set"):
            return {**self.existing, **dict(zip(
                [part.split("=", 1)[0] for part in self.sql.split(" set ", 1)[1].split(" where ", 1)[0].split(",")],
                self.params,
            ))}
        return None


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class RateCardValidationTests(unittest.TestCase):
    def test_create_cannot_bypass_draft_activation_workflow(self):
        with self.assertRaises(ValidationError):
            payload(status="active")

    def test_percentage_fee_requires_percentage_and_no_amount(self):
        with self.assertRaises(ValueError):
            _validate_terms({"rate_basis": "percentage_fee", "fee_percentage": None, "rate_amount": None,
                             "effective_from": date(2026, 1, 1), "effective_to": None})

    def test_end_date_cannot_precede_start_date(self):
        with self.assertRaises(ValueError):
            _validate_terms({"rate_basis": "fixed_fee", "rate_amount": Decimal("100"),
                             "fee_percentage": None, "effective_from": date(2026, 2, 1),
                             "effective_to": date(2026, 1, 1)})

    def test_percentage_cannot_be_used_with_fixed_rate(self):
        with self.assertRaises(ValueError):
            _validate_terms({"rate_basis": "fixed_fee", "rate_amount": Decimal("100"),
                             "fee_percentage": Decimal("10"), "effective_from": date(2026, 1, 1),
                             "effective_to": None})


class RateCardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_rejects_whitespace_only_name_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "two non-space"):
            await RateCardService().create_rate_card(payload(name="  "), ACTOR)

    async def test_create_allocates_next_version_and_attributes_actor(self):
        cursor = FakeCursor(version=3)

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.rate_card_service.get_connection", fake_connection):
            result = await RateCardService().create_rate_card(payload(name="  Permanent placement  "), ACTOR)

        self.assertEqual(result["version"], 4)
        self.assertEqual(result["name"], "Permanent placement")
        self.assertEqual(cursor.inserted["created_by"], ACTOR)
        self.assertTrue(any("pg_advisory_xact_lock" in sql for sql, _ in cursor.queries))
        self.assertTrue(any("select set_config('app.actor_user_id'" in sql for sql, _ in cursor.queries))

    async def test_create_rejects_client_outside_organisation(self):
        cursor = FakeCursor(client_exists=False)

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.rate_card_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "same organisation"):
                await RateCardService().create_rate_card(payload(), ACTOR)
        self.assertFalse(any(sql.startswith("insert into public.rate_cards") for sql, _ in cursor.queries))

    async def test_active_rate_card_must_be_expired_before_archiving(self):
        existing = {
            "id": CARD, "organization_id": ORG, "client_id": CLIENT, "job_id": None,
            "name": "Permanent placement", "employment_type": "permanent",
            "rate_basis": "percentage_fee", "currency": "GBP", "rate_amount": None,
            "fee_percentage": Decimal("15"), "effective_from": date(2026, 10, 1),
            "effective_to": None, "status": "active", "version": 1, "notes": None,
            "created_by": ACTOR, "created_at": NOW, "updated_at": NOW,
        }
        cursor = FakeCursor(existing=existing)

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.rate_card_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "Invalid rate-card status transition"):
                await RateCardService().update_rate_card(ORG, CARD, RateCardUpdate(status="archived"), ACTOR)
        self.assertFalse(any(sql.startswith("update public.rate_cards set") for sql, _ in cursor.queries))

    async def test_active_commercial_terms_are_immutable(self):
        existing = {
            "id": CARD, "organization_id": ORG, "client_id": CLIENT, "job_id": None,
            "name": "Permanent placement", "employment_type": "permanent",
            "rate_basis": "percentage_fee", "currency": "GBP", "rate_amount": None,
            "fee_percentage": Decimal("15"), "effective_from": date(2026, 10, 1),
            "effective_to": None, "status": "active", "version": 1, "notes": None,
            "created_by": ACTOR, "created_at": NOW, "updated_at": NOW,
        }
        cursor = FakeCursor(existing=existing)

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.rate_card_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "immutable"):
                await RateCardService().update_rate_card(
                    ORG, CARD, RateCardUpdate(fee_percentage=Decimal("18")), ACTOR
                )
        self.assertFalse(any(sql.startswith("update public.rate_cards set") for sql, _ in cursor.queries))

    async def test_activation_rejects_overlapping_active_version(self):
        existing = {
            "id": CARD, "organization_id": ORG, "client_id": CLIENT, "job_id": None,
            "name": "Permanent placement", "employment_type": "permanent",
            "rate_basis": "percentage_fee", "currency": "GBP", "rate_amount": None,
            "fee_percentage": Decimal("15"), "effective_from": date(2026, 10, 1),
            "effective_to": None, "status": "draft", "version": 2, "notes": None,
            "created_by": ACTOR, "created_at": NOW, "updated_at": NOW,
        }
        cursor = FakeCursor(existing=existing, overlap={"id": UUID("55555555-5555-4555-8555-555555555555")})

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        with patch("app.services.rate_card_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "overlaps"):
                await RateCardService().update_rate_card(ORG, CARD, RateCardUpdate(status="active"), ACTOR)
        self.assertFalse(any(sql.startswith("update public.rate_cards set") for sql, _ in cursor.queries))


if __name__ == "__main__":
    unittest.main()
