from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.job_distribution import DistributionChannelOut, DistributionSave
from app.services.google_indexing import notify_google_indexing

router = APIRouter(prefix="/api/jobs", tags=["job distribution"])
VALID_CHANNELS = {"careers", "google", "linkedin", "indeed", "monster", "other"}


@router.get("/{job_id}/distribution", response_model=list[DistributionChannelOut])
async def get_job_distribution(
    job_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id from public.jobs where id = %s",
                    [job_id],
                )
                job = cursor.fetchone()
                if job is None or job["organization_id"] != organization_id:
                    raise HTTPException(status_code=404, detail="Job not found")
                cursor.execute(
                    """select organization_id, job_id, channel_id, selected, status,
                              updated_by, created_at, updated_at
                       from public.job_distribution_channels
                       where organization_id = %s and job_id = %s
                       order by channel_id""",
                    [organization_id, job_id],
                )
                return [DistributionChannelOut.model_validate(row) for row in cursor.fetchall()]
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc


@router.put("/{job_id}/distribution", response_model=list[DistributionChannelOut])
async def save_job_distribution(
    job_id: UUID,
    payload: DistributionSave,
    organization_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    channel_ids = [item.channel_id for item in payload.channels]
    if len(channel_ids) != len(set(channel_ids)):
        raise HTTPException(status_code=422, detail="Each distribution channel can only appear once")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id, status from public.jobs where id = %s",
                    [job_id],
                )
                job = cursor.fetchone()
                if job is None or job["organization_id"] != organization_id:
                    raise HTTPException(status_code=404, detail="Job not found")
                cursor.execute(
                    """select selected from public.job_distribution_channels
                       where organization_id = %s and job_id = %s and channel_id = 'google'""",
                    [organization_id, job_id],
                )
                previous_google = cursor.fetchone()
                was_google_selected = bool(previous_google and previous_google["selected"])
                google_item = next((item for item in payload.channels if item.channel_id == "google"), None)
                is_google_selected = bool(google_item and google_item.selected)
                for item in payload.channels:
                    if not item.selected:
                        status = "not_selected"
                    elif item.channel_id == "careers":
                        status = "ready"
                    elif item.channel_id == "google":
                        status = "needs_public_page"
                    else:
                        status = "integration_required"
                    cursor.execute(
                        """insert into public.job_distribution_channels
                               (organization_id, job_id, channel_id, selected, status, updated_by)
                           values (%s, %s, %s, %s, %s, %s)
                           on conflict (job_id, channel_id) do update set
                               selected = excluded.selected,
                               status = excluded.status,
                               updated_by = excluded.updated_by,
                               updated_at = now()
                           returning organization_id, job_id, channel_id, selected, status,
                                     updated_by, created_at, updated_at""",
                        [organization_id, job_id, item.channel_id, item.selected, status, user_id],
                    )
                cursor.execute(
                    """select organization_id, job_id, channel_id, selected, status,
                              updated_by, created_at, updated_at
                       from public.job_distribution_channels
                       where organization_id = %s and job_id = %s
                       order by channel_id""",
                    [organization_id, job_id],
                )
                saved = [DistributionChannelOut.model_validate(row) for row in cursor.fetchall()]
                if job["status"] == "open" and is_google_selected:
                    background_tasks.add_task(notify_google_indexing, str(job_id), "URL_UPDATED")
                elif was_google_selected and not is_google_selected:
                    background_tasks.add_task(
                        notify_google_indexing, str(job_id), "URL_DELETED", True
                    )
                return saved
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Database operation failed") from exc
