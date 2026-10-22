import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.interview_scorecards import (
    CompetencyInput,
    InterviewFeedbackDraft,
    InterviewKitDefinition,
    ScorecardResponseInput,
)


class InterviewScorecardSchemaTests(unittest.TestCase):
    def test_kit_requires_at_least_one_competency(self):
        with self.assertRaises(ValidationError):
            InterviewKitDefinition(name="Engineer", competencies=[])

    def test_kit_rejects_duplicate_competency_keys(self):
        item = {"key": "communication", "name": "Communication", "description": "Clear explanation"}
        with self.assertRaises(ValidationError):
            InterviewKitDefinition(name="Engineer", competencies=[item, item])

    def test_question_and_competency_are_bounded(self):
        with self.assertRaises(ValidationError):
            CompetencyInput(key="x", name="x", description="x", questions=[
                {"question": "x"} for _ in range(13)
            ])

    def test_rating_must_be_between_one_and_five(self):
        with self.assertRaises(ValidationError):
            ScorecardResponseInput(competency_id=uuid4(), rating=6, evidence="Concrete example")

    def test_feedback_rejects_duplicate_competency_responses(self):
        competency_id = uuid4()
        response = {"competency_id": competency_id, "rating": 4, "evidence": "Explained a relevant example"}
        with self.assertRaises(ValidationError):
            InterviewFeedbackDraft(template_id=uuid4(), responses=[response, response])

    def test_feedback_requires_evidence(self):
        with self.assertRaises(ValidationError):
            ScorecardResponseInput(competency_id=uuid4(), rating=4, evidence=" ")


if __name__ == "__main__":
    unittest.main()
