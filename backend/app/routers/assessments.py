import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError

from app.auth import assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.schemas.assessments import (
    AssessmentAssignmentCreate, AssessmentAssignmentOut, AssessmentAssignmentUpdate,
    AssessmentResultCreate, AssessmentReviewCreate, AssessmentSubmissionCreate,
    AssessmentTemplateCreate, AssessmentTemplateOut, AssessmentTemplateUpdate,
    ProviderResultPayload,
)

router = APIRouter(prefix="/api/assessments", tags=["assessments"])
MANAGER_ROLES = {"owner", "admin", "recruiter", "hiring_manager"}
TEMPLATE_COLUMNS = """id, organization_id, job_id, name, description, assessment_type,
 instructions, evaluation_guidance, role_requirements, accessibility_options, provider_key,
 status, created_by, created_at, updated_at"""
ASSIGNMENT_COLUMNS = """id, organization_id, application_id, template_id, status, assigned_by,
 due_at, extended_due_at, extension_reason, accommodation_requested, accommodation_arrangements,
 instructions_snapshot, provider_key, provider_assignment_ref, assigned_at, started_at,
 submitted_at, created_at, updated_at"""


def unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Assessment service is temporarily unavailable")


def require_manager(user_id: UUID, organization_id: UUID) -> None:
    role = get_org_role(user_id, organization_id)
    if role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Recruiter or hiring-manager access required")


def record_event(cursor, organization_id: UUID, assignment_id: UUID, actor_id: UUID | None,
                 event_type: str, metadata: dict) -> None:
    cursor.execute(
        """insert into public.assessment_assignment_events
           (organization_id, assignment_id, actor_user_id, event_type, metadata)
           values (%s,%s,%s,%s,%s::jsonb)""",
        [organization_id, assignment_id, actor_id, event_type, json.dumps(metadata)],
    )
    cursor.execute(
        """insert into public.audit_events
           (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
           values (%s,%s,%s,'assessment_assignment',%s,%s::jsonb)""",
        [organization_id, actor_id, event_type, assignment_id, json.dumps(metadata)],
    )


@router.get("/templates", response_model=list[AssessmentTemplateOut])
async def list_templates(
    organization_id: UUID,
    job_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(draft|published|archived)$"),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    query = f"select {TEMPLATE_COLUMNS} from public.assessment_templates where organization_id=%s"
    params: list = [organization_id]
    if job_id:
        query += " and (job_id=%s or job_id is null)"
        params.append(job_id)
    if status:
        query += " and status=%s"
        params.append(status)
    query += " order by updated_at desc"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [AssessmentTemplateOut.model_validate(row) for row in cur.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/templates", response_model=AssessmentTemplateOut, status_code=201)
async def create_template(payload: AssessmentTemplateCreate, user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, payload.organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if payload.job_id:
                    cur.execute("select 1 from public.jobs where id=%s and organization_id=%s",
                                [payload.job_id, payload.organization_id])
                    if cur.fetchone() is None:
                        raise HTTPException(status_code=404, detail="Job not found")
                cur.execute(
                    f"""insert into public.assessment_templates
                    (organization_id, job_id, name, description, assessment_type, instructions,
                     evaluation_guidance, role_requirements, accessibility_options, provider_key, created_by, updated_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    returning {TEMPLATE_COLUMNS}""",
                    [payload.organization_id, payload.job_id, payload.name.strip(), payload.description,
                     payload.assessment_type, payload.instructions.strip(), payload.evaluation_guidance,
                     payload.role_requirements, json.dumps(payload.accessibility_options), payload.provider_key,
                     user_id, user_id],
                )
                return AssessmentTemplateOut.model_validate(cur.fetchone())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.patch("/templates/{template_id}", response_model=AssessmentTemplateOut)
async def update_template(template_id: UUID, payload: AssessmentTemplateUpdate,
                          organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No changes supplied")
    if "status" in data and data["status"] == "published":
        raise HTTPException(status_code=422, detail="Use the publish action after validating role requirements")
    if "accessibility_options" in data and data["accessibility_options"] is not None:
        data["accessibility_options"] = json.dumps(data["accessibility_options"])
    if "role_requirements" in data and data["role_requirements"] is not None:
        if any(not x.strip() for x in data["role_requirements"]):
            raise HTTPException(status_code=422, detail="Role requirements cannot be blank")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("select status from public.assessment_templates where id=%s and organization_id=%s",
                            [template_id, organization_id])
                existing = cur.fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Assessment template not found")
                if existing["status"] != "draft":
                    raise HTTPException(status_code=409, detail="Only draft templates can be edited")
                assignments = [f"{key}=%s::jsonb" if key == "accessibility_options" else f"{key}=%s" for key in data]
                cur.execute(
                    f"update public.assessment_templates set {','.join(assignments)}, updated_by=%s, updated_at=now() where id=%s and organization_id=%s returning {TEMPLATE_COLUMNS}",
                    [*data.values(), user_id, template_id, organization_id],
                )
                return AssessmentTemplateOut.model_validate(cur.fetchone())
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/templates/{template_id}/publish", response_model=AssessmentTemplateOut)
async def publish_template(template_id: UUID, organization_id: UUID,
                           user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""update public.assessment_templates
                    set status='published', updated_by=%s, updated_at=now()
                    where id=%s and organization_id=%s and status='draft'
                      and cardinality(role_requirements) > 0
                    returning {TEMPLATE_COLUMNS}""",
                    [user_id, template_id, organization_id],
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute("select status, role_requirements from public.assessment_templates where id=%s and organization_id=%s",
                                [template_id, organization_id])
                    existing = cur.fetchone()
                    if existing is None:
                        raise HTTPException(status_code=404, detail="Assessment template not found")
                    if existing["status"] != "draft":
                        raise HTTPException(status_code=409, detail="Only draft templates can be published")
                    raise HTTPException(status_code=422, detail="Add at least one role requirement before publishing")
                return AssessmentTemplateOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.get("/assignments", response_model=list[AssessmentAssignmentOut])
async def list_assignments(
    organization_id: UUID,
    application_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(assigned|in_progress|submitted|under_review|completed|cancelled|expired|provider_error)$"),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    query = f"select {ASSIGNMENT_COLUMNS} from public.assessment_assignments where organization_id=%s"
    params: list = [organization_id]
    if application_id:
        query += " and application_id=%s"; params.append(application_id)
    if status:
        query += " and status=%s"; params.append(status)
    query += " order by assigned_at desc"
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [AssessmentAssignmentOut.model_validate(row) for row in cur.fetchall()]
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/assignments", response_model=AssessmentAssignmentOut, status_code=201)
async def assign_assessment(payload: AssessmentAssignmentCreate, user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, payload.organization_id)
    if payload.due_at and payload.due_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Deadline must be in the future")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if payload.idempotency_key:
                    cur.execute(f"select {ASSIGNMENT_COLUMNS} from public.assessment_assignments where organization_id=%s and idempotency_key=%s",
                                [payload.organization_id, payload.idempotency_key])
                    existing = cur.fetchone()
                    if existing:
                        return AssessmentAssignmentOut.model_validate(existing)
                cur.execute(
                    """select a.id, a.job_id, t.id as template_id, t.status as template_status,
                              t.instructions, t.assessment_type, t.provider_key, t.job_id as template_job_id
                       from public.applications a
                       join public.assessment_templates t on t.id=%s and t.organization_id=a.organization_id
                       where a.id=%s and a.organization_id=%s""",
                    [payload.template_id, payload.application_id, payload.organization_id],
                )
                linked = cur.fetchone()
                if linked is None:
                    raise HTTPException(status_code=404, detail="Application or assessment template not found")
                if linked["template_status"] != "published":
                    raise HTTPException(status_code=409, detail="Only published assessments can be assigned")
                if linked["template_job_id"] and linked["template_job_id"] != linked["job_id"]:
                    raise HTTPException(status_code=422, detail="This assessment is configured for a different job")
                if payload.accommodation_arrangements and not payload.accommodation_requested:
                    raise HTTPException(status_code=422, detail="Mark an accommodation request before recording arrangements")
                cur.execute(
                    f"""insert into public.assessment_assignments
                    (organization_id, application_id, template_id, assigned_by, due_at, idempotency_key,
                     accommodation_requested, accommodation_arrangements, instructions_snapshot, provider_key)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    returning {ASSIGNMENT_COLUMNS}""",
                    [payload.organization_id, payload.application_id, payload.template_id, user_id, payload.due_at,
                     payload.idempotency_key, payload.accommodation_requested, payload.accommodation_arrangements,
                     linked["instructions"], linked["provider_key"]],
                )
                row = cur.fetchone()
                record_event(cur, payload.organization_id, row["id"], user_id, "assessment_assigned",
                             {"template_id": str(payload.template_id), "application_id": str(payload.application_id),
                              "due_at": payload.due_at.isoformat() if payload.due_at else None,
                              "accommodation_requested": payload.accommodation_requested})
                return AssessmentAssignmentOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.patch("/assignments/{assignment_id}", response_model=AssessmentAssignmentOut)
async def update_assignment(assignment_id: UUID, payload: AssessmentAssignmentUpdate,
                            organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No changes supplied")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"select {ASSIGNMENT_COLUMNS} from public.assessment_assignments where id=%s and organization_id=%s for update",
                            [assignment_id, organization_id])
                existing = cur.fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Assessment assignment not found")
                if existing["status"] in {"completed", "cancelled", "expired"}:
                    raise HTTPException(status_code=409, detail="This assessment assignment is closed")
                metadata = {}
                if "status" in data:
                    if data["status"] != "cancelled" or existing["status"] not in {"assigned", "in_progress", "provider_error"}:
                        raise HTTPException(status_code=409, detail="That status transition is not allowed")
                    metadata["status"] = {"from": existing["status"], "to": data.pop("status")}
                if "due_at" in data:
                    new_due = data.pop("due_at")
                    reason = data.pop("extension_reason", None)
                    current_due = existing["extended_due_at"] or existing["due_at"]
                    if current_due is None or new_due is None or new_due <= current_due:
                        raise HTTPException(status_code=422, detail="An extension must move an existing deadline later")
                    if reason is None or not reason.strip():
                        raise HTTPException(status_code=422, detail="A reason is required for deadline extensions")
                    data["extended_due_at"] = new_due
                    data["extension_reason"] = reason.strip()
                    metadata["deadline_extension"] = {"from": current_due.isoformat(), "to": new_due.isoformat(), "reason": reason.strip()}
                elif "extension_reason" in data:
                    raise HTTPException(status_code=422, detail="A deadline extension requires a new due_at")
                if "accommodation_arrangements" in data and data["accommodation_arrangements"] and data.get("accommodation_requested", existing["accommodation_requested"]) is False:
                    raise HTTPException(status_code=422, detail="Mark an accommodation request before recording arrangements")
                metadata["updated_fields"] = sorted(data.keys())
                assignments = [f"{key}=%s" for key in data]
                if not assignments and not metadata.get("status"):
                    raise HTTPException(status_code=422, detail="No valid changes supplied")
                if metadata.get("status"):
                    data["status"] = metadata["status"]["to"]
                    assignments.append("status=%s")
                cur.execute(
                    f"update public.assessment_assignments set {','.join(assignments)}, updated_at=now() where id=%s and organization_id=%s returning {ASSIGNMENT_COLUMNS}",
                    [*data.values(), assignment_id, organization_id],
                )
                row = cur.fetchone()
                record_event(cur, organization_id, assignment_id, user_id,
                             "assessment_deadline_extended" if "deadline_extension" in metadata else "assessment_assignment_updated",
                             metadata)
                return AssessmentAssignmentOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/assignments/{assignment_id}/start", response_model=AssessmentAssignmentOut)
async def start_assessment(assignment_id: UUID, organization_id: UUID,
                           user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""update public.assessment_assignments set status='in_progress',
                    started_at=coalesce(started_at,now()), updated_at=now()
                    where id=%s and organization_id=%s and status='assigned'
                    returning {ASSIGNMENT_COLUMNS}""", [assignment_id, organization_id])
                row = cur.fetchone()
                if row is None:
                    cur.execute(f"select {ASSIGNMENT_COLUMNS} from public.assessment_assignments where id=%s and organization_id=%s",
                                [assignment_id, organization_id])
                    existing = cur.fetchone()
                    if existing is None: raise HTTPException(status_code=404, detail="Assessment assignment not found")
                    if existing["status"] != "in_progress": raise HTTPException(status_code=409, detail="Assessment cannot be started in its current status")
                    return AssessmentAssignmentOut.model_validate(existing)
                record_event(cur, organization_id, assignment_id, user_id, "assessment_started", {})
                return AssessmentAssignmentOut.model_validate(row)
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/assignments/{assignment_id}/submissions", status_code=201)
async def submit_assessment(assignment_id: UUID, payload: AssessmentSubmissionCreate,
                            organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""select aa.*, t.assessment_type from public.assessment_assignments aa
                    join public.assessment_templates t on t.id=aa.template_id and t.organization_id=aa.organization_id
                    where aa.id=%s and aa.organization_id=%s for update of aa""", [assignment_id, organization_id])
                assignment = cur.fetchone()
                if assignment is None: raise HTTPException(status_code=404, detail="Assessment assignment not found")
                if assignment["status"] not in {"assigned", "in_progress"}:
                    raise HTTPException(status_code=409, detail="This assessment is not accepting submissions")
                deadline = assignment["extended_due_at"] or assignment["due_at"]
                if deadline and deadline < datetime.now(timezone.utc):
                    cur.execute("update public.assessment_assignments set status='expired', updated_at=now() where id=%s and organization_id=%s", [assignment_id, organization_id])
                    record_event(cur, organization_id, assignment_id, user_id, "assessment_expired", {"deadline": deadline.isoformat()})
                    conn.commit()
                    raise HTTPException(status_code=409, detail="The assessment deadline has passed")
                if payload.submission_type != assignment["assessment_type"]:
                    raise HTTPException(status_code=422, detail="Submission type must match the assigned assessment")
                cur.execute(
                    """insert into public.assessment_submissions
                    (organization_id, assignment_id, submission_type, text_content, provider_submission_ref, metadata)
                    values (%s,%s,%s,%s,%s,%s::jsonb)
                    returning id, organization_id, assignment_id, submission_type, text_content, provider_submission_ref, metadata, submitted_at""",
                    [organization_id, assignment_id, payload.submission_type, payload.text_content,
                     payload.provider_submission_ref, json.dumps(payload.metadata)],
                )
                submission = cur.fetchone()
                cur.execute("update public.assessment_assignments set status='submitted', submitted_at=now(), updated_at=now() where id=%s and organization_id=%s",
                            [assignment_id, organization_id])
                record_event(cur, organization_id, assignment_id, user_id, "assessment_submitted",
                             {"submission_id": str(submission["id"]), "submission_type": payload.submission_type})
                return submission
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/assignments/{assignment_id}/results", status_code=201)
async def add_result(assignment_id: UUID, payload: AssessmentResultCreate, organization_id: UUID,
                     user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("select status from public.assessment_assignments where id=%s and organization_id=%s for update",
                            [assignment_id, organization_id])
                assignment = cur.fetchone()
                if assignment is None: raise HTTPException(status_code=404, detail="Assessment assignment not found")
                if assignment["status"] not in {"submitted", "under_review"}:
                    raise HTTPException(status_code=409, detail="A result can only be recorded after submission")
                if payload.submission_id:
                    cur.execute("select id from public.assessment_submissions where id=%s and assignment_id=%s and organization_id=%s",
                                [payload.submission_id, assignment_id, organization_id])
                    if cur.fetchone() is None: raise HTTPException(status_code=422, detail="Submission does not belong to this assignment")
                cur.execute(
                    """insert into public.assessment_results
                    (organization_id, assignment_id, submission_id, source, methodology, score, max_score,
                     summary, evidence, result_payload, created_by)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                    returning id, organization_id, assignment_id, submission_id, source, methodology, score,
                              max_score, summary, evidence, result_payload, provider_key, provider_result_ref, received_at, created_by, created_at""",
                    [organization_id, assignment_id, payload.submission_id, payload.source, payload.methodology,
                     payload.score, payload.max_score, payload.summary, json.dumps(payload.evidence),
                     json.dumps(payload.result_payload), user_id],
                )
                result = cur.fetchone()
                cur.execute("update public.assessment_assignments set status='under_review', updated_at=now() where id=%s and organization_id=%s",
                            [assignment_id, organization_id])
                record_event(cur, organization_id, assignment_id, user_id, "assessment_result_recorded",
                             {"result_id": str(result["id"]), "source": payload.source, "methodology": payload.methodology})
                return result
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/assignments/{assignment_id}/reviews", status_code=201)
async def review_result(assignment_id: UUID, payload: AssessmentReviewCreate, organization_id: UUID,
                        user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("select status from public.assessment_assignments where id=%s and organization_id=%s for update",
                            [assignment_id, organization_id])
                assignment = cur.fetchone()
                if assignment is None: raise HTTPException(status_code=404, detail="Assessment assignment not found")
                if assignment["status"] not in {"under_review", "submitted"}:
                    raise HTTPException(status_code=409, detail="Assessment is not awaiting review")
                if payload.result_id:
                    cur.execute("select id from public.assessment_results where id=%s and assignment_id=%s and organization_id=%s",
                                [payload.result_id, assignment_id, organization_id])
                    if cur.fetchone() is None: raise HTTPException(status_code=422, detail="Result does not belong to this assignment")
                cur.execute(
                    """insert into public.assessment_reviews
                    (organization_id, assignment_id, result_id, reviewer_id, feedback, recommendation)
                    values (%s,%s,%s,%s,%s,%s)
                    returning id, organization_id, assignment_id, result_id, reviewer_id, feedback, recommendation, reviewed_at""",
                    [organization_id, assignment_id, payload.result_id, user_id, payload.feedback.strip(), payload.recommendation],
                )
                review = cur.fetchone()
                cur.execute("update public.assessment_assignments set status='completed', updated_at=now() where id=%s and organization_id=%s",
                            [assignment_id, organization_id])
                record_event(cur, organization_id, assignment_id, user_id, "assessment_review_submitted",
                             {"review_id": str(review["id"]), "recommendation": payload.recommendation})
                return review
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.get("/assignments/{assignment_id}/evidence")
async def get_evidence(assignment_id: UUID, organization_id: UUID,
                       user_id: UUID = Depends(get_current_user_id)):
    require_manager(user_id, organization_id)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"select {ASSIGNMENT_COLUMNS} from public.assessment_assignments where id=%s and organization_id=%s",
                            [assignment_id, organization_id])
                assignment = cur.fetchone()
                if assignment is None: raise HTTPException(status_code=404, detail="Assessment assignment not found")
                cur.execute("""select id, submission_type, text_content, provider_submission_ref, metadata, submitted_at
                    from public.assessment_submissions where assignment_id=%s and organization_id=%s order by submitted_at desc""",
                    [assignment_id, organization_id])
                submissions = list(cur.fetchall())
                cur.execute("""select id, submission_id, source, methodology, score, max_score, summary, evidence,
                    result_payload, provider_key, provider_result_ref, received_at, created_by, created_at
                    from public.assessment_results where assignment_id=%s and organization_id=%s order by received_at desc""",
                    [assignment_id, organization_id])
                results = list(cur.fetchall())
                cur.execute("""select id, result_id, reviewer_id, feedback, recommendation, reviewed_at
                    from public.assessment_reviews where assignment_id=%s and organization_id=%s order by reviewed_at desc""",
                    [assignment_id, organization_id])
                reviews = list(cur.fetchall())
                return {"assignment": AssessmentAssignmentOut.model_validate(assignment), "submissions": submissions,
                        "results": results, "reviews": reviews}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc


@router.post("/providers/{provider_key}/webhook")
async def provider_webhook(provider_key: str, request: Request,
                           x_assessment_signature: str | None = Header(default=None),
                           x_assessment_event_id: str | None = Header(default=None)):
    if not provider_key or len(provider_key) > 100 or any(not (("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "_") for ch in provider_key):
        raise HTTPException(status_code=400, detail="Invalid provider key")
    safe_provider = provider_key.upper()
    secret = os.getenv(f"ASSESSMENT_PROVIDER_{safe_provider}_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Assessment provider webhook is not configured")
    if not x_assessment_event_id or len(x_assessment_event_id) > 255 or not x_assessment_signature:
        raise HTTPException(status_code=400, detail="Provider signature and event ID are required")
    raw = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_assessment_signature.strip()):
        raise HTTPException(status_code=401, detail="Invalid provider signature")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = ProviderResultPayload.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid provider result payload") from exc
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into public.assessment_provider_events
                    (provider_key, provider_event_id, payload_sha256, signature_verified)
                    values (%s,%s,%s,true) on conflict (provider_key, provider_event_id) do nothing
                    returning id""",
                    [provider_key, x_assessment_event_id, digest],
                )
                event = cur.fetchone()
                if event is None:
                    cur.execute("select payload_sha256 from public.assessment_provider_events where provider_key=%s and provider_event_id=%s",
                                [provider_key, x_assessment_event_id])
                    prior = cur.fetchone()
                    if prior and prior["payload_sha256"] != digest:
                        raise HTTPException(status_code=409, detail="Provider event ID was already used with a different payload")
                    return {"status": "duplicate_ignored"}
                cur.execute(
                    """select aa.id, aa.organization_id, aa.status, aa.provider_key, t.assessment_type
                    from public.assessment_assignments aa join public.assessment_templates t
                    on t.id=aa.template_id and t.organization_id=aa.organization_id
                    where aa.id=%s""",
                    [payload.assignment_id],
                )
                assignment = cur.fetchone()
                if assignment is None or assignment["provider_key"] != provider_key or assignment["assessment_type"] != "external_test":
                    cur.execute("update public.assessment_provider_events set processing_status='ignored',processed_at=now(),failure_code='assignment_mismatch' where id=%s",
                                [event["id"]])
                    return {"status": "ignored"}
                if assignment["status"] not in {"submitted", "under_review", "in_progress", "assigned"}:
                    cur.execute("update public.assessment_provider_events set processing_status='ignored',processed_at=now(),failure_code='assignment_closed' where id=%s",
                                [event["id"]])
                    return {"status": "ignored"}
                cur.execute(
                    """insert into public.assessment_results
                    (organization_id, assignment_id, source, methodology, score, max_score, summary, evidence,
                     result_payload, provider_key, provider_result_ref)
                    values (%s,%s,'provider',%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                    returning id""",
                    [assignment["organization_id"], payload.assignment_id, payload.methodology, payload.score,
                     payload.max_score, payload.summary, json.dumps(payload.evidence),
                     json.dumps({"provider": provider_key}), provider_key, payload.provider_result_ref],
                )
                cur.execute("update public.assessment_assignments set status='under_review', updated_at=now() where id=%s and organization_id=%s",
                            [payload.assignment_id, assignment["organization_id"]])
                cur.execute("update public.assessment_provider_events set processing_status='processed',processed_at=now() where id=%s",
                            [event["id"]])
                record_event(cur, assignment["organization_id"], payload.assignment_id, None,
                             "assessment_provider_result_received",
                             {"provider_key": provider_key, "provider_event_id": x_assessment_event_id})
                return {"status": "processed"}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise unavailable(exc) from exc
