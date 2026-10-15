import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError
from fastapi import HTTPException

from app import auth
from app.routers import offers, placements

from app.schemas.offers import OfferCreate, OfferOut
from app.schemas.placements import PlacementCreate, PlacementOut
from app.services.offer_service import create_offer
from app.services.placement_service import _validate_fee_terms, create_placement


ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")
APPLICATION = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("44444444-4444-4444-8444-444444444444")
JOB = UUID("55555555-5555-4555-8555-555555555555")


class FakeCursor:
    def __init__(self, application=None):
        self.application = application
        self.sql = ""
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.queries.append((self.sql, params))

    def fetchone(self):
        if "from public.applications" in self.sql:
            return self.application
        if self.sql.startswith("select client_id from public.jobs"):
            return {"client_id": None}
        if self.sql.startswith("insert into public.offers"):
            return {"id": UUID("66666666-6666-4666-8666-666666666666")}
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

    def commit(self):
        return None


class OfferPlacementWorkflowGuardTests(unittest.TestCase):
    def test_output_schemas_allow_lifecycle_statuses(self):
        offer = OfferOut.model_validate({"id": UUID("66666666-6666-4666-8666-666666666666"), "organization_id": ORG, "application_id": APPLICATION, "title": "Engineer", "status": "accepted", "sent_at": None, "responded_at": None, "created_by": USER, "created_at": "2026-10-15T00:00:00Z", "updated_at": "2026-10-15T00:00:00Z"})
        placement = PlacementOut.model_validate({"id": UUID("77777777-7777-4777-8777-777777777777"), "organization_id": ORG, "application_id": APPLICATION, "job_id": JOB, "candidate_id": CANDIDATE, "status": "active", "start_date": date(2026, 10, 15), "created_by": USER, "created_at": "2026-10-15T00:00:00Z", "updated_at": "2026-10-15T00:00:00Z"})
        self.assertEqual(offer.status, "accepted")
        self.assertEqual(placement.status, "active")

    def test_offer_creation_cannot_set_sent_or_accepted_status(self):
        for status in ("sent", "accepted"):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                OfferCreate(
                    organization_id=ORG,
                    application_id=APPLICATION,
                    title="Software Engineer",
                    status=status,
                )

    def test_percentage_placement_fee_cannot_be_stored_as_fixed_amount(self):
        with self.assertRaisesRegex(ValueError, "either a fixed fee amount"):
            _validate_fee_terms({"fee_amount": 100, "fee_percentage": 15, "fee_type": "percentage", "fee_currency": "GBP"})

    def test_fixed_placement_fee_requires_currency(self):
        with self.assertRaisesRegex(ValueError, "requires fixed fee type and a currency"):
            _validate_fee_terms({"fee_amount": 100, "fee_percentage": None, "fee_type": "fixed", "fee_currency": None})

    def test_placement_creation_cannot_set_active_or_completed_status(self):
        for status in ("active", "completed"):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                PlacementCreate(
                    organization_id=ORG,
                    application_id=APPLICATION,
                    job_id=JOB,
                    candidate_id=CANDIDATE,
                    start_date=date(2026, 10, 15),
                    status=status,
                )

    def test_offer_requires_application_at_interview_or_offer_stage(self):
        cursor = FakeCursor(application={"status": "screening"})

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        payload = OfferCreate(organization_id=ORG, application_id=APPLICATION, title="Software Engineer")
        with patch("app.services.offer_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "interview or offer stage"):
                create_offer(payload, USER)
        self.assertFalse(any(sql.startswith("insert into public.offers") for sql, _ in cursor.queries))

    def test_placement_candidate_and_job_must_match_hired_application(self):
        cursor = FakeCursor(application={"candidate_id": CANDIDATE, "job_id": JOB, "status": "hired"})

        @contextmanager
        def fake_connection():
            yield FakeConnection(cursor)

        payload = PlacementCreate(
            organization_id=ORG,
            application_id=APPLICATION,
            job_id=UUID("77777777-7777-4777-8777-777777777777"),
            candidate_id=CANDIDATE,
            start_date=date(2026, 10, 15),
        )
        with patch("app.services.placement_service.get_connection", fake_connection):
            with self.assertRaisesRegex(ValueError, "must match the application"):
                create_placement(payload, USER)
        self.assertFalse(any(sql.startswith("insert into public.placements") for sql, _ in cursor.queries))



class CommercialWorkflowAuthorizationTests(unittest.TestCase):
    def test_owner_admin_and_recruiter_can_write_commercial_workflows(self):
        for role in ("owner", "admin", "recruiter"):
            with self.subTest(role=role), patch.object(auth, "get_org_role", return_value=role):
                auth.assert_org_recruiter(USER, ORG)

    def test_viewer_and_hiring_manager_cannot_write_commercial_workflows(self):
        for role in ("viewer", "hiring_manager"):
            with self.subTest(role=role), patch.object(auth, "get_org_role", return_value=role):
                with self.assertRaises(HTTPException) as error:
                    auth.assert_org_recruiter(USER, ORG)
                self.assertEqual(error.exception.status_code, 403)

    def test_viewer_cannot_create_offer(self):
        payload = OfferCreate(organization_id=ORG, application_id=APPLICATION, title="Engineer")
        with patch.object(offers, "assert_org_recruiter", side_effect=HTTPException(403, "Recruiter access required")) as guard, patch.object(offers, "create_offer") as create:
            with self.assertRaises(HTTPException) as error:
                offers.post_offer(payload, USER)
        self.assertEqual(error.exception.status_code, 403)
        guard.assert_called_once_with(USER, ORG)
        create.assert_not_called()

    def test_viewer_cannot_create_placement(self):
        payload = PlacementCreate(
            organization_id=ORG, application_id=APPLICATION, job_id=JOB,
            candidate_id=CANDIDATE, start_date=date(2026, 10, 15),
        )
        with patch.object(placements, "assert_org_recruiter", side_effect=HTTPException(403, "Recruiter access required")) as guard, patch.object(placements, "create_placement") as create:
            with self.assertRaises(HTTPException) as error:
                placements.post_placement(payload, USER)
        self.assertEqual(error.exception.status_code, 403)
        guard.assert_called_once_with(USER, ORG)
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
