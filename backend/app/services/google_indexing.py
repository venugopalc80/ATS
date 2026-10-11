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

logger = logging.getLogger(__name__)
INDEXING_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]


def notify_google_indexing(job_id: str, notification_type: str) -> None:
    """Send URL_UPDATED or URL_DELETED without failing the underlying ATS operation."""
    if os.getenv("GOOGLE_INDEXING_ENABLED", "").lower() not in {"1", "true", "yes"}:
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
        base_url = os.getenv("NEXT_PUBLIC_SITE_URL", "https://aqerith.com").rstrip("/")
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
