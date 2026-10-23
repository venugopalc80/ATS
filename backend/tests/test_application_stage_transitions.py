import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from app.schemas.applications import ApplicationCreate, ApplicationStageConfigUpdate, ApplicationTransition
from app.services.application_service import ApplicationService, _validate_stage_config_shape


ORG = UUID("11111111-1111-4111-8111-111111111111")
JOB = UUID("33333333-3333-4333-8333-333333333333")
CANDIDATE = UUID("66666666-6666-4666-8666-666666666666")
APPLICATION = UUID("77777777-7777-4777-8777-777777777777")
USER = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 10, 22, 11, tzinfo=timezone.utc)

DEFAULT_CONFIG = [
    {"stage_key": "new", "enabled": True, "allowed_next_stages": ["screening", "rejected", "withdrawn"]},
    {"stage_key": "screening", "enabled": True, "allowed_next_stages": ["shortlisted", "submitted", "interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "shortlisted", "enabled": True, "allowed_next_stages": ["interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "submitted", "enabled": True, "allowed_next_stages": ["interview", "assessment", "rejected", "withdrawn"]},
    {"stage_key": "interview", "enabled": True, "allowed_next_stages": ["assessment", "offer", "rejected", "withdrawn"]},
    {"stage_key": "assessment", "enabled": True, "allowed_next_stages": ["interview", "offer", "rejected", "withdrawn"]},
    {"stage_key": "offer", "enabled": True, "allowed_next_stages": ["hired", "rejected", "withdrawn"]},
    {"stage_key": "hired", "enabled": True, "allowed_next_stages": []},
    {"stage_key": "rejected", "enabled": True, "allowed_next_stages": []},
    {"stage_key": "withdrawn", "enabled": True, "allowed_next_stages": []},
]


class StateCursor:
    def __init__(self, state, stage_config=None):
        self.state = state
        self.stage_config = list(stage_config if stage_config is not None else DEFAULT_CONFIG)
        self.sql = ""
        self.params = []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split()).lower()
        self.params = params or []
        self.executed.append((self.sql, self.params))
        if self.sql.startswith("update public.applications set status="):
            self.state["status"] = self.params[0]
            self.state["updated_at"] = NOW

    def fetchone(self):
        if "select status, organization_id from public.applications" in self.sql:
            return {"status": self.state["status"], "organization_id": self.state["organization_id"]}
        if "from public.applications where id=%s" in self.sql:
            return dict(self.state)
        if self.sql.startswith("update public.applications set status="):
            return dict(self.state)
        raise AssertionError(f"Unexpected fetchone query: {self.sql}")

    def fetchall(self):
        if "from public.application_stage_config" in self.sql:
            return list(self.stage_config)
        return []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class ApplicationStageTransitionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {
            "id": APPLICATION,
            "organization_id": ORG,
            "job_id": JOB,
            "candidate_id": CANDIDATE,
            "source": "careers_page",
            "status": "new",
            "match_score": None,
            "match_explanation": None,
            "human_reviewed": False,
            "human_reviewed_by": None,
            "human_reviewed_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.cursor = StateCursor(self.state)

        @contextmanager
        def fake_connection():
            with FakeConnection(self.cursor) as connection:
                yield connection

        self.connection_patch = patch("app.services.application_service.get_connection", fake_connection)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    async def test_valid_transition_sets_actor_and_reason(self):
        result = await ApplicationService().transition_application(APPLICATION, "screening", USER, "  CV reviewed  ")
        self.assertEqual(result["status"], "screening")
        self.assertIn(("select set_config('app.actor_user_id', %s, true)", [str(USER)]), self.cursor.executed)
        self.assertIn(("select set_config('app.transition_reason', %s, true)", ["CV reviewed"]), self.cursor.executed)
        self.assertTrue(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))
        self.assertTrue(any("from public.application_stage_config" in sql for sql, _ in self.cursor.executed))

    async def test_service_rejects_blank_transition_reason(self):
        with self.assertRaisesRegex(ValueError, "Transition reason cannot be blank"):
            await ApplicationService().transition_application(APPLICATION, "screening", USER, "   ")
        self.assertEqual(self.cursor.executed, [])

    async def test_service_rejects_overlong_transition_reason(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed 1,000 characters"):
            await ApplicationService().transition_application(APPLICATION, "screening", USER, "x" * 1001)
        self.assertEqual(self.cursor.executed, [])

    async def test_invalid_transition_is_rejected_without_update(self):
        with self.assertRaisesRegex(ValueError, "Invalid application stage transition"):
            await ApplicationService().transition_application(APPLICATION, "hired", USER, "Skip stages")
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    async def test_same_stage_is_idempotent_and_does_not_write(self):
        self.state["status"] = "screening"
        result = await ApplicationService().transition_application(APPLICATION, "screening", USER, "No-op")
        self.assertEqual(result["status"], "screening")
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    async def test_custom_stage_configuration_is_respected(self):
        self.cursor.stage_config = [
            {"stage_key": "new", "enabled": True, "allowed_next_stages": ["interview"]},
            {"stage_key": "interview", "enabled": True, "allowed_next_stages": ["hired"]},
            {"stage_key": "hired", "enabled": True, "allowed_next_stages": []},
        ]
        result = await ApplicationService().transition_application(APPLICATION, "interview", USER, "Urgent review")
        self.assertEqual(result["status"], "interview")

    async def test_disabled_target_stage_is_rejected(self):
        self.cursor.stage_config = [
            {"stage_key": "new", "enabled": True, "allowed_next_stages": ["screening"]},
            {"stage_key": "screening", "enabled": False, "allowed_next_stages": []},
        ]
        with self.assertRaisesRegex(ValueError, "Target application stage is disabled"):
            await ApplicationService().transition_application(APPLICATION, "screening", USER, "Stage disabled")
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    async def test_missing_stage_configuration_fails_closed(self):
        self.cursor.stage_config = []
        with self.assertRaisesRegex(ValueError, "Application stage configuration is missing"):
            await ApplicationService().transition_application(APPLICATION, "screening", USER, "Missing config")
        self.assertFalse(any(sql.startswith("update public.applications set status=") for sql, _ in self.cursor.executed))

    def test_stage_config_update_rejects_duplicate_next_stages(self):
        with self.assertRaisesRegex(ValueError, "Allowed next stages must be unique"):
            ApplicationStageConfigUpdate(allowed_next_stages=["screening", "screening"])

    def test_stage_config_update_rejects_blank_label(self):
        with self.assertRaisesRegex(ValueError, "Stage label cannot be blank"):
            ApplicationStageConfigUpdate(label="   ")

    def test_enabled_non_terminal_stage_cannot_become_a_dead_end(self):
        existing = {
            "allowed_next_stages": ["screening"],
            "is_terminal": False,
            "enabled": True,
        }
        with self.assertRaisesRegex(ValueError, "must allow at least one next stage"):
            _validate_stage_config_shape(
                "new", {"allowed_next_stages": []}, existing
            )

    def test_disabled_non_terminal_stage_may_have_no_next_stages(self):
        existing = {
            "allowed_next_stages": ["screening"],
            "is_terminal": False,
            "enabled": True,
        }
        next_stages, terminal, enabled = _validate_stage_config_shape(
            "new", {"allowed_next_stages": [], "enabled": False}, existing
        )
        self.assertEqual(next_stages, [])
        self.assertFalse(terminal)
        self.assertFalse(enabled)

    def test_terminal_stage_cannot_have_next_stages(self):
        existing = {
            "allowed_next_stages": [],
            "is_terminal": True,
            "enabled": True,
        }
        with self.assertRaisesRegex(ValueError, "Terminal stages cannot have allowed next stages"):
            _validate_stage_config_shape(
                "hired", {"allowed_next_stages": ["screening"]}, existing
            )

    def test_new_application_defaults_to_initial_stage(self):
        payload = ApplicationCreate(organization_id=ORG, job_id=JOB, candidate_id=CANDIDATE)
        self.assertEqual(payload.status, "new")

    def test_new_application_cannot_skip_audited_transition(self):
        with self.assertRaises(ValidationError):
            ApplicationCreate(
                organization_id=ORG,
                job_id=JOB,
                candidate_id=CANDIDATE,
                status="hired",
            )

    def test_transition_requires_a_reason(self):
        with self.assertRaises(ValidationError):
            ApplicationTransition(status="screening")

    def test_transition_rejects_blank_reason(self):
        with self.assertRaisesRegex(ValidationError, "Transition reason cannot be blank"):
            ApplicationTransition(status="screening", reason="   ")


if __name__ == "__main__":
    unittest.main()
