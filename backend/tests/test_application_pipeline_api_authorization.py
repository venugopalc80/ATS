import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers.applications import transition_application, update_application_stage
from app.schemas.applications import ApplicationStageConfigUpdate, ApplicationTransition
from app.services.application_service import ApplicationService


ORG = UUID("11111111-1111-4111-8111-111111111111")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")


class ApplicationPipelineAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.applications.service.transition_application", new_callable=AsyncMock)
    @patch("app.routers.applications.service.get_application_for_member", new_callable=AsyncMock)
    @patch(
        "app.routers.applications.assert_org_member",
        side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
    )
    async def test_non_member_cannot_transition_application(
        self, _assert_member, get_application, transition
    ):
        get_application.return_value = None

        with self.assertRaises(HTTPException) as raised:
            await transition_application(
                APPLICATION,
                ApplicationTransition(status="screening", reason="CV reviewed"),
                user_id=USER,
            )

        self.assertEqual(raised.exception.status_code, 404)
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


class ApplicationTenantScopedReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_read_is_scoped_by_organisation_membership_in_sql(self):
        application_id = APPLICATION
        connection = MagicMock()
        cursor = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        context = MagicMock()
        context.__enter__.return_value = connection
        context.__exit__.return_value = False
        cursor.fetchone.return_value = None

        with patch("app.services.application_service.get_connection", return_value=context):
            result = await ApplicationService().get_application_for_member(application_id, USER)

        sql, params = cursor.execute.call_args.args
        self.assertIn("from public.applications a", sql.lower())
        self.assertIn("from public.organization_members om", sql.lower())
        self.assertIn("om.organization_id=a.organization_id", sql.replace(" ", "").lower())
        self.assertIn("om.user_id=%s", sql.replace(" ", "").lower())
        self.assertEqual(params, [application_id, USER])
        self.assertIsNone(result)
