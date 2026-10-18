import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/documents", tags=["candidate documents"])
logger = logging.getLogger(__name__)
BUCKET = "candidate-documents"


def storage_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise HTTPException(status_code=503, detail="Private document storage is not configured")
    return create_client(url, key)


@router.delete("/{document_id}", status_code=204)
async def delete_candidate_document(
    document_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Soft-delete document metadata and audit it, then remove the private object.

    A retry for an already-soft-deleted document repeats storage cleanup without
    creating duplicate audit events. All metadata reads are tenant-scoped.
    """
    assert_org_member(user_id, organization_id)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select candidate_id, storage_bucket, storage_path, deleted_at
                       from public.candidate_documents
                       where id=%s and organization_id=%s""",
                    [document_id, organization_id],
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Document not found")

                if row["storage_bucket"] != BUCKET:
                    logger.error("Refusing to delete candidate document from unexpected bucket")
                    raise HTTPException(status_code=409, detail="Document storage configuration is invalid")

                if row["deleted_at"] is None:
                    cursor.execute(
                        """update public.candidate_documents
                           set deleted_at=now()
                           where id=%s and organization_id=%s and deleted_at is null""",
                        [document_id, organization_id],
                    )
                    cursor.execute(
                        """update public.candidates
                           set resume_path=null, updated_at=now()
                           where id=%s and organization_id=%s and resume_path=%s""",
                        [row["candidate_id"], organization_id, row["storage_path"]],
                    )
                    cursor.execute(
                        """insert into public.audit_events
                           (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                           values (%s,%s,'candidate_document_deleted','candidate_document',%s,%s::jsonb)""",
                        [
                            organization_id,
                            user_id,
                            document_id,
                            '{"candidate_id":"' + str(row["candidate_id"]) + '"}',
                        ],
                    )

        # Soft deletion commits first. If storage removal fails, the file is no
        # longer accessible through the API; retrying this endpoint retries cleanup.
        storage_client().storage.from_(BUCKET).remove([row["storage_path"]])
        return None
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        logger.exception("Database failure while deleting candidate document")
        raise HTTPException(status_code=503, detail="Document service unavailable; please retry shortly") from exc
    except Exception as exc:
        logger.exception("Candidate document deletion/storage cleanup failed")
        raise HTTPException(
            status_code=503,
            detail="The document is no longer available; storage cleanup is pending. Retry deletion shortly.",
        ) from exc
