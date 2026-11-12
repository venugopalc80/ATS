import unittest

from fastapi import HTTPException

from app.routers.documents import (
    _structured_cv_fields,
    cv_candidate_fields,
    validate_document_bytes,
)


class CvExtractionTests(unittest.TestCase):
    def test_extracts_contact_and_skills_without_creating_candidate(self):
        text = """Priya Sharma
        priya.sharma@example.com
        +44 7700 900123
        Skills
        Python, SQL, Docker
        Work Experience
        Software Engineer, Example Ltd, 2021-2024
        Education
        MSc Computer Science
        """
        fields = cv_candidate_fields(text, "priya-sharma.pdf")
        self.assertEqual(fields["first_name"], "Priya")
        self.assertEqual(fields["last_name"], "Sharma")
        self.assertEqual(fields["email"], "priya.sharma@example.com")
        self.assertIn("python", fields["skills"])
        self.assertIn("sql", fields["skills"])

        data, confidence, provenance = _structured_cv_fields(text, "priya-sharma.pdf")
        self.assertIn("Software Engineer", " ".join(data["work_history"]))
        self.assertIn("MSc Computer Science", " ".join(data["education"]))
        self.assertGreater(confidence["email"], confidence["first_name"])
        self.assertEqual(provenance["method"], "rule_based")

    def test_rejects_mime_mismatch_and_oversized_content(self):
        with self.assertRaises(HTTPException) as mismatch:
            validate_document_bytes(b"%PDF-1.7", "text/plain")
        self.assertEqual(mismatch.exception.status_code, 415)

        with self.assertRaises(HTTPException) as oversized:
            validate_document_bytes(b"%PDF-" + b"x" * (5 * 1024 * 1024), "application/pdf")
        self.assertEqual(oversized.exception.status_code, 413)

    def test_does_not_accept_empty_documents(self):
        with self.assertRaises(HTTPException) as empty:
            validate_document_bytes(b"", "application/pdf")
        self.assertEqual(empty.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
