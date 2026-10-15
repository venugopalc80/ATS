import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.routers import rate_cards
from app.schemas.rate_cards import RateCardCreate
from uuid import UUID
from datetime import date
from decimal import Decimal

ORG = UUID("11111111-1111-4111-8111-111111111111")
CLIENT = UUID("33333333-3333-4333-8333-333333333333")
USER = UUID("22222222-2222-4222-8222-222222222222")


class RateCardAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_cannot_create_rate_card(self):
        payload = RateCardCreate(
            organization_id=ORG,
            client_id=CLIENT,
            name="Permanent placement",
            employment_type="permanent",
            rate_basis="percentage_fee",
            currency="GBP",
            fee_percentage=Decimal("15"),
            effective_from=date(2026, 10, 1),
        )
        with patch.object(
            rate_cards, "assert_org_admin",
            side_effect=HTTPException(status_code=403, detail="Admin access required"),
        ) as membership, patch.object(rate_cards.service, "create_rate_card", new_callable=AsyncMock) as create:
            with self.assertRaises(HTTPException) as error:
                await rate_cards.create_rate_card(payload, USER)
        self.assertEqual(error.exception.status_code, 403)
        membership.assert_called_once_with(USER, ORG)
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
