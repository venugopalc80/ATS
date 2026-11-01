import unittest
from datetime import time
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException

from app.routers.application_sla import update_sla_policy
from app.schemas.application_sla import ApplicationSLAPolicyUpdate

ORG = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")


class ApplicationSLAPolicyValidationTests(unittest.TestCase):
    def test_defaults_match_initial_operational_policy(self):
        policy = ApplicationSLAPolicyUpdate(organization_id=ORG)
        self.assertEqual(policy.initial_review_minutes, 1440)
        self.assertEqual(policy.first_recruiter_action_minutes, 2880)
        self.assertEqual(policy.candidate_follow_up_minutes, 2880)
        self.assertEqual(policy.post_interview_update_minutes, 1440)
        self.assertEqual(policy.working_days, [1, 2, 3, 4, 5])

    def test_rejects_invalid_timezone(self):
        with self.assertRaises(ValueError):
            ApplicationSLAPolicyUpdate(organization_id=ORG, timezone="Not/A_Timezone")

    def test_rejects_duplicate_or_invalid_working_days(self):
        with self.assertRaises(ValueError):
            ApplicationSLAPolicyUpdate(organization_id=ORG, working_days=[1, 1])
        with self.assertRaises(ValueError):
            ApplicationSLAPolicyUpdate(organization_id=ORG, working_days=[8])

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            ApplicationSLAPolicyUpdate(
                organization_id=ORG,
                business_hours_start=time(17, 0),
                business_hours_end=time(9, 0),
            )


class ApplicationSLAPolicyAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.application_sla.assert_org_admin",
           side_effect=HTTPException(status_code=403, detail="Admin access required"))
    async def test_non_admin_cannot_change_sla_policy(self, assert_admin):
        with self.assertRaises(HTTPException) as raised:
            await update_sla_policy(
                ApplicationSLAPolicyUpdate(organization_id=ORG),
                user_id=USER,
            )
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
