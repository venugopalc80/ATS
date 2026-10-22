import unittest
from pydantic import ValidationError

from app.routers.help_onboarding import OnboardingProgressUpdate


class OnboardingProgressTests(unittest.TestCase):
    def test_known_steps_are_accepted(self):
        payload = OnboardingProgressUpdate(
            completed_steps=["workspace_created", "first_job_created"],
            dismissed=False,
        )
        self.assertEqual(payload.completed_steps, ["workspace_created", "first_job_created"])

    def test_unknown_step_is_rejected(self):
        with self.assertRaises(ValidationError):
            OnboardingProgressUpdate(completed_steps=["made_up_step"])

    def test_extra_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            OnboardingProgressUpdate(completed_steps=[], tenant_id="another-org")


if __name__ == "__main__":
    unittest.main()
