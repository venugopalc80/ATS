"""Best-effort notifications to Google's Indexing API for eligible public job URLs.

Configure GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON and GOOGLE_INDEXING_ENABLED=true on the
backend only. Google must approve/use the project quota as required before production use.
"""
import json
import logging
import os
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

logger = logging.getLogger(__name__)
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]


def notify_google_indexing(
    job_id: str,
    notification_type: str,
    preverified_publication: bool = False,
) -> None:
    """Send URL_UPDATED or URL_DELETED without failing the underlying ATS operation."""
    if os.getenv("GOOGLE_INDEXING_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return

    # A delete may cascade away both the job and its distribution row before this
    # background task runs. In that case the caller must verify publication pre-delete.
    if not preverified_publication:
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select j.status, d.selected
                           from public.jobs j
                           left join public.job_distribution_channels d
                             on d.job_id = j.id
                            and d.organization_id = j.organization_id
                            and d.channel_id = 'google'
                           where j.id = %s""",
                        [job_id],
                    )
                    publication = cursor.fetchone()
            if publication is None:
                return
            if notification_type == "URL_UPDATED":
                if publication["status"] != "open" or not publication["selected"]:
                    return
            elif not publication["selected"]:
                return
        except (DatabaseConfigurationError, DatabaseConnectionError):
            logger.exception("Unable to verify Google publication status for job %s", job_id)
            return

    raw_credentials = os.getenv("GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON")
    if not raw_credentials:
        logger.warning("Google Indexing API is enabled but service-account credentials are missing")
        return

    try:
        service_account_info = json.loads(raw_credentials)
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        session = AuthorizedSession(credentials)
        base_url = os.getenv("PUBLIC_SITE_URL", "https://aqerith.com").rstrip("/")
        job_url = f"{base_url}/careers/{quote(str(job_id), safe='')}"
        response = session.post(
            INDEXING_ENDPOINT,
            json={"url": job_url, "type": notification_type},
            timeout=15,
        )
        response.raise_for_status()
        logger.info(
            "Google Indexing API accepted %s notification for job %s",
            notification_type,
            job_id,
        )
    except Exception:
        # Job creation/update/deletion must succeed even if Google's API is unavailable.
        logger.exception("Google Indexing API notification failed for job %s", job_id)
