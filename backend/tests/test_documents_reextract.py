import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routers.documents import reextract_candidate_document


ORG_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CANDIDATE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
DOCUMENT_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


def database_context(row):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    cursor_context.__exit__.return_value = False
    connection = MagicMock()
    connection.cursor.return_value = cursor_context
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    connection_context.__exit__.return_value = False
    return connection_context


class ReextractCandidateDocumentTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.routers.documents.extract_cv_profile")
    @patch("app.routers.documents.extract_cv_text", return_value="Abhaya\\nAWS and Snowflake")
    @patch("app.routers.documents.storage_client")
    @patch("app.routers.documents.verify_candidate")
    @patch("app.routers.documents.get_connection")
    @patch("app.routers.documents.assert_org_member")
    async def test_reextract_uses_named_database_row_fields(
        self, assert_member, get_connection, verify_candidate, storage_client,
        extract_text, extract_profile,
    ):
        row = {
            "candidate_id": CANDIDATE_ID,
            "storage_bucket": "candidate-documents",
            "storage_path": f"{ORG_ID}/{CANDIDATE_ID}/{DOCUMENT_ID}.docx",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "original_filename": "Abhaya AWS-BigData-Snowflake.docx",
        }
        get_connection.return_value = database_context(row)
        storage = MagicMock()
        storage.storage.from_.return_value.download.return_value = b"docx-bytes"
        storage_client.return_value = storage
        extracted = {"first_name": "Abhaya", "skills": ["aws", "snowflake"]}
        extract_profile.return_value = extracted

        result = await reextract_candidate_document(
            document_id=DOCUMENT_ID,
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert_member.assert_called_once_with(USER_ID, ORG_ID)
        verify_candidate.assert_called_once_with(CANDIDATE_ID, ORG_ID)
        storage.storage.from_.assert_called_once_with("candidate-documents")
        storage.storage.from_.return_value.download.assert_called_once_with(row["storage_path"])
        extract_text.assert_called_once_with(b"docx-bytes", row["content_type"])
        extract_profile.assert_called_once_with("Abhaya\\nAWS and Snowflake", row["original_filename"])
        self.assertEqual(result["candidate_id"], str(CANDIDATE_ID))
        self.assertEqual(result["filename"], row["original_filename"])
        self.assertEqual(result["extracted_profile"], extracted)

    @patch("app.routers.documents.get_connection")
    @patch("app.routers.documents.assert_org_member")
    async def test_reextract_returns_404_when_document_is_missing(self, assert_member, get_connection):
        get_connection.return_value = database_context(None)

        with self.assertRaises(HTTPException) as raised:
            await reextract_candidate_document(
                document_id=DOCUMENT_ID,
                organization_id=ORG_ID,
                user_id=USER_ID,
            )

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
