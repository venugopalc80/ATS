import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_user_id
from app.main import app
from app.routers import applications


ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("99999999-9999-4999-8999-999999999999")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")
JOB = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
NOW = "2026-10-14T12:00:00+00:00"


def application_row(organization_id=ORG):
    return {
        "id": APPLICATION,
        "organization_id": organization_id,
        "job_id": JOB,
        "candidate_id": CANDIDATE,
        "source": "careers_page",
        "status": "new",
        "match_score": "88.5",
        "match_explanation": "Strong skills match; recruiter-only assessment.",
        "human_reviewed": False,
        "human_reviewed_by": None,
        "human_reviewed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


class ApplicationPipelineHttpAuthorizationTests(unittest.TestCase):
    """Exercise real FastAPI routing/serialization while isolating membership and DB boundaries."""

    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_current_user_id] = lambda: USER
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_current_user_id, None)

    def test_cross_tenant_application_read_returns_forbidden(self):
        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            return_value=application_row(OTHER_ORG),
        ) as get_application:
            with patch(
                "app.routers.applications.assert_org_member",
                side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
            ):
                response = self.client.get(f"/api/applications/{APPLICATION}")

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("match_explanation", response.text)
        get_application.assert_awaited_once_with(APPLICATION)

    def test_cross_tenant_history_read_is_denied_before_history_query(self):
        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            return_value=application_row(OTHER_ORG),
        ):
            with patch(
                "app.routers.applications.assert_org_member",
                side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
            ):
                with patch.object(
                    applications.service, "list_stage_history", new_callable=AsyncMock
                ) as list_history:
                    response = self.client.get(f"/api/applications/{APPLICATION}/history")

        self.assertEqual(response.status_code, 403)
        list_history.assert_not_awaited()

    def test_cross_tenant_transition_is_denied_before_transition_write(self):
        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            return_value=application_row(OTHER_ORG),
        ):
            with patch(
                "app.routers.applications.assert_org_member",
                side_effect=HTTPException(status_code=403, detail="Not an organisation member"),
            ):
                with patch.object(
                    applications.service, "transition_application", new_callable=AsyncMock
                ) as transition:
                    response = self.client.post(
                        f"/api/applications/{APPLICATION}/transition",
                        json={"status": "screening", "reason": "CV reviewed"},
                    )

        self.assertEqual(response.status_code, 403)
        transition.assert_not_awaited()

    def test_non_admin_cannot_write_stage_configuration_over_http(self):
        with patch(
            "app.routers.applications.assert_org_admin",
            side_effect=HTTPException(status_code=403, detail="Organisation admin required"),
        ):
            with patch.object(
                applications.service, "update_stage_config", new_callable=AsyncMock
            ) as update_stage:
                response = self.client.patch(
                    f"/api/applications/stages/screening?organization_id={ORG}",
                    json={"label": "Private review"},
                )

        self.assertEqual(response.status_code, 403)
        update_stage.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
