import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers.applications import transition_application, update_application_stage
from app.schemas.applications import ApplicationStageConfigUpdate, ApplicationTransition


ORG = UUID("11111111-1111-4111-8111-111111111111")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")


class ApplicationPipelineAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.applications.service.transition_application", new_callable=AsyncMock)
    @patch("app.routers.applications.service.get_application", new_callable=AsyncMock)
    @patch(
        "app.routers.applications.assert_org_member",
        side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
    )
    async def test_non_member_cannot_transition_application(
        self, _assert_member, get_application, transition
    ):
        get_application.return_value = {"id": APPLICATION, "organization_id": ORG}

        with self.assertRaises(HTTPException) as raised:
            await transition_application(
                APPLICATION,
                ApplicationTransition(status="screening", reason="CV reviewed"),
                user_id=USER,
            )

        self.assertEqual(raised.exception.status_code, 403)
        transition.assert_not_awaited()

    @patch("app.routers.applications.service.update_stage_config", new_callable=AsyncMock)
    @patch(
        "app.routers.applications.assert_org_admin",
        side_effect=HTTPException(status_code=403, detail="Organisation admin required"),
    )
    async def test_non_admin_cannot_update_stage_configuration(
        self, _assert_admin, update_stage_config
    ):
        with self.assertRaises(HTTPException) as raised:
            await update_application_stage(
                stage_key="screening",
                organization_id=ORG,
                payload=ApplicationStageConfigUpdate(label="Review"),
                user_id=USER,
            )

        self.assertEqual(raised.exception.status_code, 403)
        update_stage_config.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
