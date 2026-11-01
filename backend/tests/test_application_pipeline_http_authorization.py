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


    def test_bulk_transition_reports_success_and_per_application_failures(self):
        first_id = UUID("77777777-7777-4777-8777-777777777771")
        second_id = UUID("77777777-7777-4777-8777-777777777772")
        other_tenant_id = UUID("77777777-7777-4777-8777-777777777773")
        first_row = application_row()
        first_row["id"] = first_id
        second_row = application_row()
        second_row["id"] = second_id
        other_row = application_row(OTHER_ORG)
        other_row["id"] = other_tenant_id
        updated_row = dict(first_row)
        updated_row["status"] = "screening"

        with patch.object(
            applications.service, "get_application", new_callable=AsyncMock,
            side_effect=[first_row, second_row, other_row],
        ):
            with patch(
                "app.routers.applications.assert_org_member",
                side_effect=[None, None, HTTPException(status_code=403, detail="Not an organisation member")],
            ):
                with patch.object(
                    applications.service, "transition_application", new_callable=AsyncMock,
                    side_effect=[updated_row, ValueError("Invalid application stage transition")],
                ) as transition:
                    response = self.client.post(
                        "/api/applications/bulk-transition",
                        json={
                            "application_ids": [str(first_id), str(second_id), str(other_tenant_id)],
                            "status": "screening",
                            "reason": "Batch CV review",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual((payload["requested"], payload["succeeded"], payload["failed"]), (3, 1, 2))
        self.assertEqual(payload["results"][0]["status"], "screening")
        self.assertTrue(payload["results"][0]["success"])
        self.assertEqual(payload["results"][1]["error"], "Invalid application stage transition")
        self.assertEqual(payload["results"][2]["error"], "Application not found")
        self.assertEqual(transition.await_count, 2)

    def test_bulk_transition_rejects_duplicate_application_ids(self):
        response = self.client.post(
            "/api/applications/bulk-transition",
            json={
                "application_ids": [str(APPLICATION), str(APPLICATION)],
                "status": "screening",
                "reason": "Batch CV review",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_bulk_transition_rejects_more_than_one_hundred_applications(self):
        ids = [str(UUID(int=index + 1)) for index in range(101)]
        response = self.client.post(
            "/api/applications/bulk-transition",
            json={"application_ids": ids, "status": "screening", "reason": "Batch CV review"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
