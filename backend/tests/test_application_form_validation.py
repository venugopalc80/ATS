import unittest
from app.routers.public_jobs import _validate_answer
from app.routers.application_forms import QuestionIn

class ApplicationFormValidationTests(unittest.TestCase):
    def test_required_text_question_rejects_empty_value(self):
        self.assertFalse(_validate_answer({"field_type":"text","required":True}, ""))

    def test_optional_text_question_accepts_empty_value(self):
        self.assertTrue(_validate_answer({"field_type":"text","required":False}, ""))

    def test_choice_answer_must_match_published_options(self):
        question = {"field_type":"select","required":True,"options":["London","Remote"]}
        self.assertTrue(_validate_answer(question, "London"))
        self.assertFalse(_validate_answer(question, "Admin override"))

    def test_boolean_answer_is_not_coerced_from_string(self):
        self.assertTrue(_validate_answer({"field_type":"boolean","required":True}, False))
        self.assertFalse(_validate_answer({"field_type":"boolean","required":True}, "yes"))

    def test_multiple_choice_requires_known_options(self):
        question = {"field_type":"multi_select","required":True,"options":["Python","SQL"]}
        self.assertTrue(_validate_answer(question, ["Python","SQL"]))
        self.assertFalse(_validate_answer(question, ["Python","Root access"]))

    def test_question_keys_and_labels_are_validated(self):
        with self.assertRaises(ValueError):
            QuestionIn(question_key="not safe", label="Role", field_type="text")
        with self.assertRaises(ValueError):
            QuestionIn(question_key="valid_key", label="   ", field_type="text")

if __name__ == "__main__":
    unittest.main()
