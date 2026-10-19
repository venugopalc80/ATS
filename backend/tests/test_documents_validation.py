import unittest

from fastapi import HTTPException

from app.routers.documents import MAX_BYTES, extract_cv_profile, validate_document_bytes


PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentValidationTests(unittest.TestCase):
    def test_extracts_identity_role_and_profile_links(self):
        text = """Priya Sharma
        priya.sharma@example.com
        +44 7700 900123
        Senior Software Engineer
        Folkestone, Kent, UK
        https://www.linkedin.com/in/priyasharma
        https://github.com/priyasharma
        Python Django SQL
        """
        result = extract_cv_profile(text, "resume.pdf")
        self.assertEqual(result["first_name"], "Priya")
        self.assertEqual(result["last_name"], "Sharma")
        self.assertEqual(result["email"], "priya.sharma@example.com")
        self.assertEqual(result["current_title"], "Senior Software Engineer")
        self.assertEqual(result["location"]["city"], "Folkestone")
        self.assertEqual(result["location"]["region"], "Kent")
        self.assertEqual([item["type"] for item in result["links"]], ["linkedin", "github"])
        self.assertTrue(all(item["url"].startswith("https://") for item in result["links"]))
        self.assertTrue(result["review_required"])

    def test_empty_text_does_not_guess_candidate_name_from_filename(self):
        result = extract_cv_profile("", "john_smith_resume.pdf")
        self.assertEqual(result["first_name"], "")
        self.assertIsNone(result["last_name"])
        self.assertIsNone(result["email"])
        self.assertEqual(result["links"], [])

    def test_extracts_program_coordinator_role(self):
        text = "Venu Gopal Chowdary Ravi\\nProgram Coordinator\\nvenu@example.com\\nFolkestone, Kent, UK"
        result = extract_cv_profile(text, "program-cordinater.docx")
        self.assertEqual(result["current_title"], "Program Coordinator")

    def test_nonempty_cv_without_a_detected_name_does_not_use_filename_as_name(self):
        text = "Professional Summary\\nExperienced professional with broad business skills.\\ncontact@example.com"
        result = extract_cv_profile(text, "program-cordinater.docx")
        self.assertEqual(result["first_name"], "")
        self.assertIsNone(result["last_name"])
        self.assertEqual(result["email"], "contact@example.com")

    def test_marks_empty_text_for_ocr_review(self):
        result = extract_cv_profile("", "candidate.pdf")
        self.assertTrue(result["ocr_required"])
        self.assertTrue(result["review_required"])

    def test_accepts_pdf_signature(self):
        self.assertEqual(validate_document_bytes(b"%PDF-1.7\nbody", PDF), ".pdf")

    def test_accepts_docx_container_signature(self):
        self.assertEqual(validate_document_bytes(b"PK\x03\x04body", DOCX), ".docx")

    def test_rejects_unlisted_mime_type(self):
        with self.assertRaises(HTTPException) as error:
            validate_document_bytes(b"%PDF-1.7", "text/plain")
        self.assertEqual(error.exception.status_code, 415)

    def test_rejects_empty_file(self):
        with self.assertRaises(HTTPException) as error:
            validate_document_bytes(b"", PDF)
        self.assertEqual(error.exception.status_code, 422)

    def test_rejects_file_larger_than_five_mib(self):
        with self.assertRaises(HTTPException) as error:
            validate_document_bytes(b"%PDF-" + b"x" * MAX_BYTES, PDF)
        self.assertEqual(error.exception.status_code, 413)

    def test_rejects_mismatched_signature(self):
        with self.assertRaises(HTTPException) as error:
            validate_document_bytes(b"not a pdf", PDF)
        self.assertEqual(error.exception.status_code, 415)


if __name__ == "__main__":
    unittest.main()
