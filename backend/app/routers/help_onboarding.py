from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(tags=["help and onboarding"])

OnboardingStep = Literal[
    "workspace_created",
    "profile_reviewed",
    "first_job_created",
    "first_candidate_added",
    "first_application_created",
    "team_access_reviewed",
]


class OnboardingProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed_steps: list[OnboardingStep] | None = Field(default=None, max_length=6)
    dismissed: bool | None = None


@router.get("/api/onboarding/progress")
async def get_onboarding_progress(
    organization_id: UUID = Query(...),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select completed_steps, dismissed, updated_at
                       from public.onboarding_progress
                       where organization_id=%s and user_id=%s""",
                    [organization_id, user_id],
                )
                row = cursor.fetchone()
        return {
            "organization_id": str(organization_id),
            "completed_steps": row["completed_steps"] if row else [],
            "dismissed": row["dismissed"] if row else False,
            "updated_at": row["updated_at"] if row else None,
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Onboarding progress is unavailable") from exc


@router.patch("/api/onboarding/progress")
async def update_onboarding_progress(
    organization_id: UUID = Query(...),
    payload: OnboardingProgressUpdate = ...,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    if payload.completed_steps is None and payload.dismissed is None:
        raise HTTPException(status_code=400, detail="Provide progress steps or dismissal state")

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select completed_steps, dismissed
                       from public.onboarding_progress
                       where organization_id=%s and user_id=%s for update""",
                    [organization_id, user_id],
                )
                current = cursor.fetchone()
                steps = list(current["completed_steps"]) if current else []
                dismissed = bool(current["dismissed"]) if current else False
                if payload.completed_steps is not None:
                    steps = list(dict.fromkeys(payload.completed_steps))
                if payload.dismissed is not None:
                    dismissed = payload.dismissed
                cursor.execute(
                    """insert into public.onboarding_progress
                       (organization_id, user_id, completed_steps, dismissed, updated_at)
                       values (%s, %s, %s::jsonb, %s, now())
                       on conflict (organization_id, user_id) do update
                         set completed_steps=excluded.completed_steps,
                             dismissed=excluded.dismissed,
                             updated_at=now()
                       returning completed_steps, dismissed, updated_at""",
                    [organization_id, user_id, __import__("json").dumps(steps), dismissed],
                )
                row = cursor.fetchone()
        return {
            "organization_id": str(organization_id),
            "completed_steps": row["completed_steps"],
            "dismissed": row["dismissed"],
            "updated_at": row["updated_at"],
        }
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Onboarding progress is unavailable") from exc


@router.get("/api/help")
async def search_help_articles(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=60),
    locale: str = Query(default="en-GB", min_length=2, max_length=10),
    limit: int = Query(default=20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user_id),
):
    query = (q or "").strip()
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """with latest as (
                         select distinct on (slug, locale)
                           id, slug, locale, version, title, category, summary,
                           body_markdown, updated_at
                         from public.help_articles
                         where published=true and locale=%s
                         order by slug, locale, version desc
                       )
                       select id, slug, locale, version, title, category,
                              summary, body_markdown, updated_at
                       from latest
                       where (%s = '' or title ilike %s or summary ilike %s or body_markdown ilike %s)
                         and (%s::text is null or category ilike %s)
                       order by category, title
                       limit %s""",
                    [
                        locale,
                        query,
                        f"%{query}%",
                        f"%{query}%",
                        f"%{query}%",
                        category,
                        category,
                        limit,
                    ],
                )
                articles = list(cursor.fetchall())
        return {"articles": articles}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Help centre is unavailable") from exc
