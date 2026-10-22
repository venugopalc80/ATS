from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import assert_org_admin, assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.interview_scorecards import InterviewFeedbackDraft, InterviewKitCreate, InterviewKitDefinition
from app.services import interview_scorecard_service as service

router = APIRouter(tags=["interview-scorecards"])


def _database_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


def _handle_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail="Invalid scorecard request")


@router.get("/api/interview-kits")
def get_interview_kits(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        return service.list_kits(organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/api/interview-kits", status_code=201)
def post_interview_kit(payload: InterviewKitCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        return service.create_kit(payload.organization_id, user_id, payload.job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/api/interview-kits/{kit_id}/versions", status_code=201)
def post_interview_kit_version(
    kit_id: UUID, organization_id: UUID, payload: InterviewKitDefinition,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        result = service.create_version(organization_id, kit_id, user_id, payload)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Interview kit not found")
    return result


@router.post("/api/interview-kits/{kit_id}/publish")
def post_publish_interview_kit(
    kit_id: UUID, organization_id: UUID, template_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        result = service.publish_kit(organization_id, kit_id, template_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Kit or draft version not found")
    return result


@router.get("/api/interviews/{interview_id}/scorecard-template")
def get_scorecard_template(interview_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        # Resolve the interview's organisation before checking membership.
        from app.db import get_connection
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.interviews where id=%s", [interview_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        organization_id = row["organization_id"]
        assert_org_member(user_id, organization_id)
        result = service.get_template_for_interview(organization_id, interview_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        return result
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("/api/interviews/{interview_id}/scorecards", status_code=201)
def save_scorecard_draft(
    interview_id: UUID, payload: InterviewFeedbackDraft,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        from app.db import get_connection
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.interviews where id=%s", [interview_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        organization_id = row["organization_id"]
        assert_org_member(user_id, organization_id)
        return service.save_feedback(organization_id, interview_id, user_id, payload, submit=False)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    except (LookupError, PermissionError, ValueError) as exc:
        raise _handle_service_error(exc) from exc


@router.post("/api/interviews/{interview_id}/scorecards/submit")
def submit_scorecard(
    interview_id: UUID, payload: InterviewFeedbackDraft,
    user_id: UUID = Depends(get_current_user_id),
):
    try:
        from app.db import get_connection
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.interviews where id=%s", [interview_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        organization_id = row["organization_id"]
        assert_org_member(user_id, organization_id)
        return service.save_feedback(organization_id, interview_id, user_id, payload, submit=True)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    except (LookupError, PermissionError, ValueError) as exc:
        raise _handle_service_error(exc) from exc


@router.get("/api/interviews/{interview_id}/scorecard-review")
def get_scorecard_review(interview_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        from app.db import get_connection
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.interviews where id=%s", [interview_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        organization_id = row["organization_id"]
        assert_org_member(user_id, organization_id)
        role = get_org_role(user_id, organization_id)
        result = service.review_feedback(
            organization_id, interview_id, user_id, can_review_early=role in {"owner", "admin"}
        )
        return result
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    except (LookupError, PermissionError, ValueError) as exc:
        raise _handle_service_error(exc) from exc


@router.get("/api/interviews/{interview_id}/scorecards/me")
def get_my_scorecard(interview_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    try:
        from app.db import get_connection
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select organization_id from public.interviews where id=%s", [interview_id])
                row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        organization_id = row["organization_id"]
        assert_org_member(user_id, organization_id)
        return service.get_my_feedback(organization_id, interview_id, user_id)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    except (LookupError, PermissionError, ValueError) as exc:
        raise _handle_service_error(exc) from exc
