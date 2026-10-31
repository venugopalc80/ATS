import unittest
import asyncio
from io import BytesIO

from fastapi import HTTPException, UploadFile

from app.routers.documents import MAX_BULK_BYTES, MAX_BYTES, read_bulk_cv_files

from app.routers.documents import validate_document_bytes


PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentValidationTests(unittest.TestCase):
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

    def test_bulk_batch_limit_uses_actual_bytes_when_upload_size_is_unknown(self):
        async def run():
            first = UploadFile(filename="one.pdf", file=BytesIO(b"a" * (MAX_BULK_BYTES // 2 + 1)))
            second = UploadFile(filename="two.pdf", file=BytesIO(b"b" * (MAX_BULK_BYTES // 2 + 1)))
            with self.assertRaises(HTTPException) as error:
                await read_bulk_cv_files([first, second])
            self.assertEqual(error.exception.status_code, 413)
            self.assertTrue(first.file.closed)
            self.assertTrue(second.file.closed)

        asyncio.run(run())

    def test_bulk_batch_accepts_actual_bytes_within_aggregate_limit(self):
        async def run():
            first = UploadFile(filename="one.pdf", file=BytesIO(b"a" * 1024))
            second = UploadFile(filename="two.pdf", file=BytesIO(b"b" * 1024))
            payloads = await read_bulk_cv_files([first, second])
            self.assertEqual([len(item) for item in payloads], [1024, 1024])
            await first.close()
            await second.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
