from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/candidate-portal", tags=["candidate portal"])


def _verified_email(user) -> str | None:
    """Return the authenticated email only when Supabase marks it confirmed."""
    email = getattr(user, "email", None)
    confirmed_at = getattr(user, "email_confirmed_at", None) or getattr(user, "confirmed_at", None)
    if not email or not confirmed_at:
        return None
    normalized = str(email).strip().lower()
    if "@" not in normalized or any(ch.isspace() for ch in normalized):
        return None
    return normalized


def _candidate_link(user_id: UUID, organization_id: UUID):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select candidate_id
                   from public.candidate_portal_accounts
                   where user_id=%s and organization_id=%s""",
                [user_id, organization_id],
            )
            return cursor.fetchone()


@router.post("/link", status_code=202)
async def link_candidate_account(
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),
):
    """Link only the verified Auth email to one unambiguous candidate in this tenant."""
    email = _verified_email(user)
    if email is None:
        raise HTTPException(status_code=403, detail="Verify your email address before linking a candidate account")

    user_id = UUID(str(user.id))
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select id
                       from public.candidates
                       where organization_id=%s and lower(email)=lower(%s)
                       limit 2""",
                    [organization_id, email],
                )
                matches = cursor.fetchall()
                # Deliberately do not disclose whether a candidate exists or is already linked.
                if len(matches) != 1:
                    return JSONResponse(
                        status_code=202,
                        content={"message": "If your verified email matches an eligible application, portal access will be available."},
                    )

                candidate_id = matches[0]["id"]
                cursor.execute(
                    """insert into public.candidate_portal_accounts
                       (organization_id, candidate_id, user_id)
                       values (%s,%s,%s)
                       on conflict do nothing
                       returning id""",
                    [organization_id, candidate_id, user_id],
                )
                inserted = cursor.fetchone()
                if inserted:
                    cursor.execute(
                        """insert into public.audit_events
                           (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                           values (%s,%s,'candidate_portal_account_linked',
                                   'candidate_portal_account',%s,
                                   jsonb_build_object('candidate_id',%s::text))""",
                        [organization_id, user_id, inserted["id"], candidate_id],
                    )
                else:
                    cursor.execute(
                        """select id from public.candidate_portal_accounts
                           where organization_id=%s and candidate_id=%s and user_id=%s""",
                        [organization_id, candidate_id, user_id],
                    )
                    # Idempotent retries are accepted; conflicting links remain opaque.
                    cursor.fetchone()
        return JSONResponse(
            status_code=202,
            content={"message": "If your verified email matches an eligible application, portal access will be available."},
        )
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Candidate portal is temporarily unavailable") from exc


def _require_link(user_id: UUID, organization_id: UUID) -> UUID:
    try:
        link = _candidate_link(user_id, organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Candidate portal is temporarily unavailable") from exc
    if link is None:
        raise HTTPException(status_code=404, detail="Candidate portal account not found")
    return UUID(str(link["candidate_id"]))


@router.get("/me")
async def get_candidate_portal_profile(
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),
):
    user_id = UUID(str(user.id))
    candidate_id = _require_link(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select first_name, last_name, email, phone, city, region,
                              country_code, current_title, years_experience, skills
                       from public.candidates
                       where id=%s and organization_id=%s""",
                    [candidate_id, organization_id],
                )
                profile = cursor.fetchone()
                if profile is None:
                    raise HTTPException(status_code=404, detail="Candidate portal account not found")
                return {"profile": profile}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Candidate portal is temporarily unavailable") from exc


@router.get("/applications")
async def list_candidate_portal_applications(
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),
):
    user_id = UUID(str(user.id))
    candidate_id = _require_link(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select a.id, a.status, a.created_at, a.updated_at,
                              j.title as job_title, j.location, j.country_code,
                              j.employment_type, j.work_mode
                       from public.applications a
                       join public.jobs j
                         on j.id=a.job_id and j.organization_id=a.organization_id
                       where a.organization_id=%s and a.candidate_id=%s
                       order by a.created_at desc""",
                    [organization_id, candidate_id],
                )
                return {"applications": list(cursor.fetchall())}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Candidate portal is temporarily unavailable") from exc


@router.get("/applications/{application_id}")
async def get_candidate_portal_application(
    application_id: UUID,
    organization_id: UUID = Query(...),
    user=Depends(get_current_user),
):
    user_id = UUID(str(user.id))
    candidate_id = _require_link(user_id, organization_id)
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select a.id, a.status, a.created_at, a.updated_at,
                              j.title as job_title, j.description as job_description,
                              j.location, j.country_code, j.employment_type, j.work_mode
                       from public.applications a
                       join public.jobs j
                         on j.id=a.job_id and j.organization_id=a.organization_id
                       where a.id=%s and a.organization_id=%s and a.candidate_id=%s""",
                    [application_id, organization_id, candidate_id],
                )
                application = cursor.fetchone()
                if application is None:
                    raise HTTPException(status_code=404, detail="Application not found")
                return {"application": application}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Candidate portal is temporarily unavailable") from exc
