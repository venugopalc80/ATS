import unittest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.routers.document_deletion import delete_candidate_document

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DOC = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
CANDIDATE = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PATH = f"{ORG}/{CANDIDATE}/{DOC}.pdf"


class DocumentDeletionTests(unittest.IsolatedAsyncioTestCase):
    def setup_mocks(self, deleted_at=None, bucket="candidate-documents"):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "candidate_id": CANDIDATE,
            "storage_bucket": bucket,
            "storage_path": PATH,
            "deleted_at": deleted_at,
        }
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        connection.cursor.return_value.__exit__.return_value = False
        db_context = MagicMock()
        db_context.__enter__.return_value = connection
        db_context.__exit__.return_value = False
        storage = MagicMock()
        storage.storage.from_.return_value.remove.return_value = {}
        return cursor, db_context, storage

    async def test_deletion_is_tenant_scoped_and_audited(self):
        cursor, db_context, storage = self.setup_mocks()
        with patch("app.routers.document_deletion.assert_org_member") as member, \
             patch("app.routers.document_deletion.get_connection", return_value=db_context), \
             patch("app.routers.document_deletion.storage_client", return_value=storage):
            result = await delete_candidate_document(DOC, ORG, USER)

        self.assertIsNone(result)
        member.assert_called_once_with(USER, ORG)
        self.assertEqual(cursor.execute.call_args_list[0].args[1], [DOC, ORG])
        self.assertTrue(any("candidate_document_deleted" in str(call) for call in cursor.execute.call_args_list))
        storage.storage.from_.assert_called_once_with("candidate-documents")
        storage.storage.from_.return_value.remove.assert_called_once_with([PATH])

    async def test_unknown_document_returns_404(self):
        cursor, db_context, storage = self.setup_mocks()
        cursor.fetchone.return_value = None
        with patch("app.routers.document_deletion.assert_org_member"), \
             patch("app.routers.document_deletion.get_connection", return_value=db_context), \
             patch("app.routers.document_deletion.storage_client", return_value=storage):
            with self.assertRaises(HTTPException) as error:
                await delete_candidate_document(DOC, ORG, USER)
        self.assertEqual(error.exception.status_code, 404)
        storage.storage.from_.assert_not_called()

    async def test_refuses_unexpected_storage_bucket(self):
        cursor, db_context, storage = self.setup_mocks(bucket="public")
        with patch("app.routers.document_deletion.assert_org_member"), \
             patch("app.routers.document_deletion.get_connection", return_value=db_context), \
             patch("app.routers.document_deletion.storage_client", return_value=storage):
            with self.assertRaises(HTTPException) as error:
                delete_candidate_document(DOC, ORG, USER)
        self.assertEqual(error.exception.status_code, 409)
        storage.storage.from_.assert_not_called()

    async def test_retry_for_soft_deleted_document_retries_storage_cleanup_without_audit(self):
        cursor, db_context, storage = self.setup_mocks(deleted_at=datetime.now(timezone.utc))
        with patch("app.routers.document_deletion.assert_org_member"), \
             patch("app.routers.document_deletion.get_connection", return_value=db_context), \
             patch("app.routers.document_deletion.storage_client", return_value=storage):
            result = await delete_candidate_document(DOC, ORG, USER)

        self.assertIsNone(result)
        self.assertFalse(any("candidate_document_deleted" in str(call) for call in cursor.execute.call_args_list))
        storage.storage.from_.return_value.remove.assert_called_once_with([PATH])


if __name__ == "__main__":
    unittest.main()
