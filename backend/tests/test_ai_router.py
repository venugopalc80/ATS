import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.ai import GenerateInput, RecommendationInput, ReviewInput, router


class AIRouterContractTests(unittest.TestCase):
    def test_router_registers_ai_endpoints(self):
        paths = {route.path for route in router.routes if hasattr(route, "path")}
        self.assertIn("/api/ai/assistant", paths)
        self.assertIn("/api/ai/governance/evaluations", paths)
        self.assertIn("/api/ai/job-description-versions/{version_id}/publish", paths)

    def test_generate_request_requires_valid_task(self):
        with self.assertRaises(ValueError):
            GenerateInput(organization_id=uuid4(), task="reject_candidate")

    def test_recommendation_requires_source_references_and_evidence(self):
        with self.assertRaises(ValueError):
            RecommendationInput(
                organization_id=uuid4(),
                object_type="candidate",
                object_id=uuid4(),
                purpose="A test recommendation purpose",
                input_references=[],
                evidence=[],
                explanation="A test explanation based on source data",
            )


class _NotFoundCursor:
    """Minimal cursor double: no record exists in the requested tenant."""
    def __init__(self):
        self.query = ""
        self.params = None
        self.calls = []

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        self.calls.append((query, params))

    def fetchone(self):
        return None


class TenantScopedEvidenceTests(unittest.TestCase):
    def test_each_evidence_lookup_is_scoped_to_requested_organization(self):
        from fastapi import HTTPException
        from app.routers.ai import _load_evidence

        org_id = uuid4()
        cases = [
            ("candidate", {"candidate_id": uuid4()}),
            ("job", {"job_id": uuid4()}),
            ("application", {"application_id": uuid4()}),
            ("interview", {"interview_id": uuid4()}),
            ("recommendation", {"recommendation_id": uuid4()}),
        ]

        for label, field in cases:
            with self.subTest(record_type=label):
                cursor = _NotFoundCursor()
                payload = GenerateInput(
                    organization_id=org_id,
                    task="answer_authorized_records",
                    **field,
                )
                with self.assertRaises(HTTPException) as caught:
                    _load_evidence(cursor, payload)

                self.assertEqual(caught.exception.status_code, 404)
                self.assertEqual(len(cursor.calls), 1)
                query, params = cursor.calls[0]
                self.assertIn("organization_id=%s", query.lower())
                self.assertEqual(params[-1], org_id)
                self.assertNotIn("select *", query.lower())

    def test_candidate_from_another_organization_is_not_returned_as_evidence(self):
        from fastapi import HTTPException
        from app.routers.ai import _load_evidence

        org_a = uuid4()
        candidate_owned_by_org_b = uuid4()
        cursor = _NotFoundCursor()
        payload = GenerateInput(
            organization_id=org_a,
            task="summarize_candidate",
            candidate_id=candidate_owned_by_org_b,
        )

        with self.assertRaises(HTTPException) as caught:
            _load_evidence(cursor, payload)

        self.assertEqual(caught.exception.status_code, 404)
        query, params = cursor.calls[0]
        self.assertIn("where id=%s and organization_id=%s", query.lower())
        self.assertEqual(params, [candidate_owned_by_org_b, org_a])




class AIRoleGuardTests(unittest.TestCase):
    def test_viewer_cannot_summarize_candidate(self):
        import asyncio
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.routers.ai import assistant

        organization_id = uuid4()
        user_id = uuid4()
        payload = GenerateInput(
            organization_id=organization_id,
            task="summarize_candidate",
            candidate_id=uuid4(),
        )
        with patch("app.routers.ai.assert_org_member") as member_check:
            with patch("app.routers.ai.get_org_role", return_value="viewer"):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(assistant(payload, user_id=user_id))

        self.assertEqual(caught.exception.status_code, 403)
        member_check.assert_called_once_with(user_id, organization_id)

    def test_viewer_cannot_prepare_interview_questions(self):
        import asyncio
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.routers.ai import assistant

        organization_id = uuid4()
        payload = GenerateInput(
            organization_id=organization_id,
            task="interview_questions",
            job_id=uuid4(),
        )
        with patch("app.routers.ai.assert_org_member"):
            with patch("app.routers.ai.get_org_role", return_value="viewer"):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(assistant(payload, user_id=uuid4()))

        self.assertEqual(caught.exception.status_code, 403)



class HumanReviewAuditTests(unittest.TestCase):
    def _assert_review_reason_is_audited(self, endpoint_name, row, entity_id):
        import asyncio
        import json
        from unittest.mock import MagicMock, patch
        from app.routers.ai import review_job_description, review_interview_kit

        organization_id = uuid4()
        user_id = uuid4()
        reason = "Reviewer changed the draft because it included an unsupported requirement"
        payload = ReviewInput(
            organization_id=organization_id,
            approved=False,
            override_reason=reason,
        )
        cursor = MagicMock()
        cursor.fetchone.return_value = row
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_cm

        endpoint = review_job_description if endpoint_name == "job_description" else review_interview_kit
        endpoint_args = (entity_id, payload)
        with patch("app.routers.ai.assert_org_member"):
            with patch("app.routers.ai.get_org_role", return_value="recruiter"):
                with patch("app.routers.ai.get_connection", return_value=connection):
                    asyncio.run(endpoint(*endpoint_args, user_id=user_id))

        audit_call = cursor.execute.call_args_list[-1]
        metadata = json.loads(audit_call.args[1][-1])
        self.assertEqual(metadata["override_reason"], reason)
        self.assertFalse(metadata["approved"])

    def test_job_description_review_reason_is_audited(self):
        entity_id = uuid4()
        self._assert_review_reason_is_audited(
            "job_description",
            {"id": entity_id, "job_id": uuid4(), "version_number": 2, "status": "in_review",
             "reviewed_by": uuid4(), "reviewed_at": "2026-10-22T12:00:00Z"},
            entity_id,
        )

    def test_interview_kit_review_reason_is_audited(self):
        entity_id = uuid4()
        self._assert_review_reason_is_audited(
            "interview_kit",
            {"id": entity_id, "job_id": uuid4(), "version_number": 2, "status": "in_review",
             "reviewed_by": uuid4(), "reviewed_at": "2026-10-22T12:00:00Z"},
            entity_id,
        )



class ModelApprovalGateTests(unittest.TestCase):
    def _call_approval(self, model_row, evaluation_row):
        import asyncio
        from unittest.mock import MagicMock, patch
        from fastapi import HTTPException
        from app.routers.ai import approve_model

        organization_id = uuid4()
        model_id = uuid4()
        user_id = uuid4()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [model_row, evaluation_row]
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_cm
        with patch("app.routers.ai.assert_org_admin"):
            with patch("app.routers.ai.get_connection", return_value=connection):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(approve_model(model_id, organization_id, user_id=user_id))
        return caught.exception, cursor

    def test_model_cannot_be_approved_without_data_processing_approval(self):
        error, cursor = self._call_approval(
            {"id": uuid4(), "data_processing_approved": False, "status": "draft"},
            None,
        )
        self.assertEqual(error.status_code, 409)
        self.assertIn("data-processing approval", error.detail)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_model_cannot_be_approved_without_passing_evaluation(self):
        error, cursor = self._call_approval(
            {"id": uuid4(), "data_processing_approved": True, "status": "draft"},
            None,
        )
        self.assertEqual(error.status_code, 409)
        self.assertIn("passing evaluation", error.detail)
        self.assertEqual(cursor.execute.call_count, 2)


class FairnessAuditCautionTests(unittest.TestCase):
    def test_small_sample_groups_are_flagged_in_uncertainty_notes(self):
        import asyncio
        import json
        from unittest.mock import MagicMock, patch
        from app.routers.ai import FairnessAuditInput, create_fairness_audit

        organization_id = uuid4()
        user_id = uuid4()
        audit_id = uuid4()
        payload = FairnessAuditInput(
            organization_id=organization_id,
            audit_name="Quarterly selection-rate review",
            dataset_version="dataset-2026-Q3",
            methodology="Compare aggregate selection rates across approved groups.",
            outcome_metric="selection_rate",
            aggregate_results={"overall": {"selection_rate": 0.32}},
            sample_sizes={"group_a": 7, "group_b": 120},
            missingness={},
            legal_review_reference="review-record-2026-03",
        )
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"id": audit_id, "audit_name": payload.audit_name},
            None,
        ]
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor_cm
        with patch("app.routers.ai.assert_org_admin"):
            with patch("app.routers.ai.get_connection", return_value=connection):
                asyncio.run(create_fairness_audit(payload, user_id=user_id))

        stored_notes = json.loads(cursor.execute.call_args_list[0].args[1][8])
        self.assertTrue(any("group_a" in note and "Small or invalid sample sizes" in note for note in stored_notes))
        audit_metadata = json.loads(cursor.execute.call_args_list[1].args[1][3])
        self.assertEqual(audit_metadata["small_sample_groups"], ["group_a"])


if __name__ == "__main__":
    unittest.main()
