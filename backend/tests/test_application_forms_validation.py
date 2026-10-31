import unittest
from fastapi import HTTPException
from app.routers.application_forms import QuestionIn, _insert_questions

class FormQuestionValidationTests(unittest.TestCase):
    def test_question_key_must_be_safe_identifier(self):
        with self.assertRaises(ValueError):
            QuestionIn(question_key="bad key", label="Question", field_type="text")

    def test_choice_question_requires_options_at_insert(self):
        class Cursor:
            def execute(self, *_args):
                raise AssertionError("Invalid choice question must be rejected before SQL")
        with self.assertRaises(HTTPException) as error:
            _insert_questions(Cursor(), "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", [QuestionIn(question_key="choice", label="Choose", field_type="select")])
        self.assertEqual(error.exception.status_code, 422)

    def test_duplicate_question_keys_are_rejected(self):
        q1 = QuestionIn(question_key="work_auth", label="Work authorisation", field_type="boolean")
        q2 = QuestionIn(question_key="work_auth", label="Another question", field_type="boolean")
        with self.assertRaises(HTTPException) as error:
            _insert_questions(object(), "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", [q1, q2])
        self.assertEqual(error.exception.status_code, 422)

if __name__ == "__main__":
    unittest.main()
