import unittest

from fastapi import HTTPException

from app.routers.documents import MAX_BYTES, _cv_sections, extract_cv_profile, validate_document_bytes


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
        text = "Venu Gopal Chowdary Ravi\nProgram Coordinator\nvenu@example.com\nFolkestone, Kent, UK"
        result = extract_cv_profile(text, "program-cordinater.docx")
        self.assertEqual(result["current_title"], "Program Coordinator")

    def test_nonempty_cv_without_a_detected_name_does_not_use_filename_as_name(self):
        text = "Professional Summary\nExperienced professional with broad business skills.\ncontact@example.com"
        result = extract_cv_profile(text, "program-cordinater.docx")
        self.assertEqual(result["first_name"], "")
        self.assertIsNone(result["last_name"])
        self.assertEqual(result["email"], "contact@example.com")

    def test_role_heading_is_not_mistaken_for_candidate_name(self):
        text = "Program Coordinator\nvenu@example.com\nFolkestone, Kent, UK"
        result = extract_cv_profile(text, "program-cordinater.docx")
        self.assertEqual(result["first_name"], "")
        self.assertIsNone(result["last_name"])
        self.assertEqual(result["current_title"], "Program Coordinator")

    def test_candidate_name_is_still_found_after_role_heading(self):
        text = "Program Coordinator\nVenu Gopal Chowdary\nvenu@example.com"
        result = extract_cv_profile(text, "resume.docx")
        self.assertEqual(result["first_name"], "Venu")
        self.assertEqual(result["last_name"], "Gopal Chowdary")

    def test_marks_empty_text_for_ocr_review(self):
        result = extract_cv_profile("", "candidate.pdf")
        self.assertTrue(result["ocr_required"])
        self.assertTrue(result["review_required"])

    def test_extracts_structured_cv_sections_for_review(self):
        text = """WORK EXPERIENCE
        Program Coordinator | Acunor
        Jan 2023 - Present
        Coordinated programme delivery and reporting.
        EDUCATION
        MSc Computer Science | Coventry University
        2024 - 2025
        CERTIFICATIONS
        AWS Certified Cloud Practitioner
        LANGUAGES
        English - Fluent
        Telugu - Native
        """
        result = _cv_sections(text)
        self.assertTrue(any(row["job_title"] == "Program Coordinator" and row["employer_name"] == "Acunor" and row["is_current"] and row["start_date"] == "2023-01-01" for row in result["employment"]))
        self.assertTrue(any("MSc Computer Science" in row["qualification"] and row["institution_name"] == "Coventry University" for row in result["education"]))
        self.assertTrue(any(row["name"] == "AWS Certified Cloud Practitioner" for row in result["certifications"]))
        self.assertTrue(any(row["language"] == "English" and row["proficiency"] == "fluent" for row in result["languages"]))

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


    def test_extracts_education_when_institution_precedes_qualification(self):
        text = """EDUCATION
        Coventry University, UK
        MSc Computer Science Sep 2024– Sep 2025
        """
        result = _cv_sections(text)
        self.assertEqual(len(result["education"]), 1)
        row = result["education"][0]
        self.assertEqual(row["institution_name"], "Coventry University, UK")
        self.assertEqual(row["qualification"], "MSc Computer Science")
        self.assertEqual(row["start_date"], "2024-09-01")
        self.assertEqual(row["end_date"], "2025-09-01")

    def test_keeps_multiple_program_coordinator_employers_separate(self):
        text = """WORK EXPERIENCE
        Program Coordinator | Acunor
        Oct 2023 – Sep 2024
        Program Coordinator | TekWissen
        Feb 2023 – Oct 2023
        Program Coordinator | Artmac
        Nov 2021 – Feb 2023
        """
        result = _cv_sections(text)
        roles = [row for row in result["employment"] if row["job_title"] == "Program Coordinator"]
        self.assertEqual(
            [(row["employer_name"], row["start_date"], row["end_date"]) for row in roles],
            [
                ("Acunor", "2023-10-01", "2024-09-01"),
                ("TekWissen", "2023-02-01", "2023-10-01"),
                ("Artmac", "2021-11-01", "2023-02-01"),
            ],
        )
        self.assertTrue(all(row["description"] is None for row in roles))

    def test_extracts_description_for_single_employment_record(self):
        text = """WORK EXPERIENCE
        Software Engineer | Example Ltd
        Jan 2022 – Mar 2024
        Built Python APIs and maintained automated tests.
        Collaborated with product and QA teams.
        """
        result = _cv_sections(text)
        role = next(row for row in result["employment"] if row["employer_name"] == "Example Ltd")
        self.assertIn("Built Python APIs", role["description"])
        self.assertIn("Collaborated with product and QA teams", role["description"])


    def test_skills_heading_is_not_mistaken_for_candidate_name(self):
        text = """CORE SKILLS
        Python SQL AWS
        Priya Sharma
        priya@example.com
        """
        result = extract_cv_profile(text, "resume.pdf")
        self.assertEqual(result["first_name"], "Priya")
        self.assertEqual(result["last_name"], "Sharma")

    def test_extracts_single_word_name_and_data_engineering_skills(self):
        text = """Abhaya
        Email: abhaya@example.com
        Phone: +1 408-789-7830
        PROFESSIONAL SUMMARY
        AWS Cloud and Hadoop Developer with Snowflake, dbt, Oracle E-Business Suite,
        ETL, data warehousing, data engineering and data governance experience.
        CORE SKILLS
        AWS Hadoop Snowflake dbt Oracle SQL
        """
        result = extract_cv_profile(text, "Abhaya AWS-BigData-Snowflake.docx")
        self.assertEqual(result["first_name"], "Abhaya")
        self.assertIsNone(result["last_name"])
        self.assertEqual(result["email"], "abhaya@example.com")
        for skill in ("aws", "hadoop", "snowflake", "dbt", "oracle e-business suite", "etl", "data warehousing", "data engineering", "data governance"):
            self.assertIn(skill, result["skills"])


if __name__ == "__main__":
    unittest.main()
