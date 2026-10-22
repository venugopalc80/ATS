from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id, get_org_role
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection
from app.services.ai_service import ALLOWED_TASKS, PROMPT_VERSION, fingerprint, generate_text

router = APIRouter(prefix="/api/ai", tags=["responsible-ai"])


class UseCaseInput(BaseModel):
    use_case_key: Literal[
        "recruitment_assistant", "job_description_writer", "interview_preparation",
        "explainable_recommendations", "fairness_monitoring", "model_governance"
    ]
    name: str = Field(min_length=2, max_length=120)
    purpose: str = Field(min_length=10, max_length=2000)
    provider_approved: bool = False
    enabled: bool = False
    approval_status: Literal["pending", "approved", "suspended", "retired"] = "pending"
    retention_days: int = Field(default=90, ge=1, le=3650)
    limitations: list[str] = Field(default_factory=list, max_length=30)


class ModelInput(BaseModel):
    provider: str = Field(min_length=2, max_length=80)
    model_name: str = Field(min_length=2, max_length=120)
    model_version: str = Field(min_length=1, max_length=120)
    intended_purpose: str = Field(min_length=10, max_length=2000)
    data_processing_approved: bool = False
    status: Literal["draft", "evaluating", "disabled", "retired"] = "draft"
    limitations: list[str] = Field(default_factory=list, max_length=30)


class GenerateInput(BaseModel):
    organization_id: UUID
    task: Literal[
        "summarize_candidate", "extract_job_requirements", "draft_candidate_message",
        "draft_job_description", "interview_questions", "explain_recommendation",
        "answer_authorized_records"
    ]
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    application_id: UUID | None = None
    interview_id: UUID | None = None
    recommendation_id: UUID | None = None
    user_request: str | None = Field(default=None, max_length=4000)


class FeedbackInput(BaseModel):
    organization_id: UUID
    feedback_status: Literal["helpful", "incorrect", "unsafe", "other"]
    feedback_text: str | None = Field(default=None, max_length=4000)


class ReviewInput(BaseModel):
    organization_id: UUID
    approved: bool
    override_reason: str | None = Field(default=None, max_length=2000)


class RecommendationInput(BaseModel):
    organization_id: UUID
    object_type: Literal["candidate", "application", "job", "interview", "job_description"]
    object_id: UUID
    purpose: str = Field(min_length=10, max_length=2000)
    input_references: list[dict] = Field(min_length=1, max_length=100)
    evidence: list[dict] = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=10, max_length=6000)
    limitations: list[str] = Field(default_factory=list, max_length=50)
    model_version_id: UUID


def _db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="AI service database operation failed")


@router.get("/governance")
async def governance(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """select id, use_case_key, name, purpose, provider_approved, enabled,
                          approval_status, limitations, retention_days, created_at, updated_at
                   from public.ai_use_cases where organization_id=%s order by use_case_key""",
                [organization_id],
            )
            use_cases = list(cur.fetchall())
            cur.execute(
                """select id, provider, model_name, model_version, prompt_version, intended_purpose,
                          data_processing_approved, status, limitations, approved_by, approved_at, created_at
                   from public.ai_model_versions where organization_id=%s order by created_at desc""",
                [organization_id],
            )
            models = list(cur.fetchall())
            cur.execute(
                """select id, suite_name, dataset_version, status, pass_criteria, summary, started_at, completed_at
                   from public.ai_evaluation_runs where organization_id=%s order by started_at desc limit 100""",
                [organization_id],
            )
            evaluations = list(cur.fetchall())
            cur.execute(
                """select id, severity, category, description, status, remediation, created_at, resolved_at
                   from public.ai_incidents where organization_id=%s order by created_at desc limit 100""",
                [organization_id],
            )
            incidents = list(cur.fetchall())
        return {"use_cases": use_cases, "models": models, "evaluations": evaluations, "incidents": incidents}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.put("/governance/use-cases")
async def upsert_use_case(
    organization_id: UUID,
    payload: UseCaseInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """insert into public.ai_use_cases
                     (organization_id, use_case_key, name, purpose, owner_user_id, provider_approved,
                      enabled, approval_status, limitations, retention_days, updated_at)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,now())
                   on conflict (organization_id, use_case_key) do update set
                     name=excluded.name, purpose=excluded.purpose, owner_user_id=excluded.owner_user_id,
                     provider_approved=excluded.provider_approved, enabled=excluded.enabled,
                     approval_status=excluded.approval_status, limitations=excluded.limitations,
                     retention_days=excluded.retention_days, updated_at=now()
                   returning id, use_case_key, name, provider_approved, enabled, approval_status, retention_days""",
                [organization_id, payload.use_case_key, payload.name, payload.purpose, user_id,
                 payload.provider_approved, payload.enabled, payload.approval_status,
                 json.dumps(payload.limitations), payload.retention_days],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_use_case_configured','ai_use_case',%s,%s::jsonb)""",
                [organization_id, user_id, row["id"], json.dumps({"key": payload.use_case_key, "enabled": payload.enabled,
                 "approval_status": payload.approval_status, "provider_approved": payload.provider_approved})],
            )
            return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/governance/models", status_code=201)
async def register_model(
    organization_id: UUID,
    payload: ModelInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, organization_id)
    # Approved model records are an explicit admin attestation, not inferred from provider availability.
    approved_at = datetime.now(timezone.utc) if payload.status == "approved" and payload.data_processing_approved else None
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """insert into public.ai_model_versions
                   (organization_id, provider, model_name, model_version, prompt_version, intended_purpose,
                    data_processing_approved, status, limitations, created_by, approved_by, approved_at,
                    configuration_fingerprint)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                   returning id, provider, model_name, model_version, prompt_version, status,
                             data_processing_approved, approved_at""",
                [organization_id, payload.provider, payload.model_name, payload.model_version, PROMPT_VERSION,
                 payload.intended_purpose, payload.data_processing_approved, payload.status,
                 json.dumps(payload.limitations), user_id,
                 user_id if approved_at else None, approved_at,
                 fingerprint({"provider": payload.provider, "model": payload.model_name,
                              "model_version": payload.model_version, "prompt_version": PROMPT_VERSION})],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_model_registered','ai_model_version',%s,%s::jsonb)""",
                [organization_id, user_id, row["id"], json.dumps({"provider": payload.provider,
                 "model": payload.model_name, "version": payload.model_version, "status": payload.status,
                 "data_processing_approved": payload.data_processing_approved})],
            )
            return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


def _load_evidence(cur, payload: GenerateInput) -> tuple[list[dict], list[dict]]:
    evidence: list[dict] = []
    refs: list[dict] = []
    if payload.recommendation_id:
        cur.execute(
            """select id, object_type, object_id, purpose, input_references, evidence, explanation,
                      limitations, model_version_id, created_at
               from public.ai_recommendations where id=%s and organization_id=%s""",
            [payload.recommendation_id, payload.organization_id],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        # Do not invent a post-hoc rationale: require the recorded process and evidence to exist.
        if not row.get("input_references") or not row.get("evidence") or not row.get("purpose"):
            raise HTTPException(status_code=409, detail="This recommendation lacks the recorded inputs required for a faithful explanation")
        evidence.append({"record_type": "recorded_ai_recommendation", **row})
        refs.append({"record_type": "ai_recommendation", "id": str(row["id"]), "fields": ["purpose", "input_references", "evidence", "limitations", "model_version_id"]})
    if payload.candidate_id:
        cur.execute(
            """select id, first_name, last_name, current_title, city, region, country_code,
                      years_experience, skills, resume_text, status
               from public.candidates where id=%s and organization_id=%s and status <> 'do_not_contact'""",
            [payload.candidate_id, payload.organization_id],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Candidate not found or unavailable")
        # CV text is sensitive; it is passed only after the provider/data approval gates below.
        row["resume_text"] = (row.get("resume_text") or "")[:15000]
        evidence.append({"record_type": "candidate", **row})
        refs.append({"record_type": "candidate", "id": str(row["id"]), "fields": ["profile", "skills", "resume_text"]})
    if payload.job_id:
        cur.execute(
            """select id, title, description, location, country_code, employment_type, work_mode,
                      salary_min, salary_max, salary_currency, experience_min, experience_max,
                      required_skills, preferred_skills, status
               from public.jobs where id=%s and organization_id=%s""",
            [payload.job_id, payload.organization_id],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        evidence.append({"record_type": "job", **row})
        refs.append({"record_type": "job", "id": str(row["id"]), "fields": ["title", "description", "requirements"]})
    if payload.application_id:
        cur.execute(
            """select id, candidate_id, job_id, status, source, created_at
               from public.applications where id=%s and organization_id=%s""",
            [payload.application_id, payload.organization_id],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Application not found")
        evidence.append({"record_type": "application", **row})
        refs.append({"record_type": "application", "id": str(row["id"]), "fields": ["status", "source", "created_at"]})
    if payload.interview_id:
        cur.execute(
            """select i.id, i.application_id, i.scheduled_at, i.duration_minutes, i.interview_type,
                      i.status, i.notes, i.feedback, j.id as job_id, j.title as job_title, j.description as job_description
               from public.interviews i
               join public.applications a on a.id=i.application_id and a.organization_id=i.organization_id
               join public.jobs j on j.id=a.job_id and j.organization_id=a.organization_id
               where i.id=%s and i.organization_id=%s""",
            [payload.interview_id, payload.organization_id],
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Interview not found")
        evidence.append({"record_type": "interview", **row})
        refs.append({"record_type": "interview", "id": str(row["id"]), "fields": ["schedule", "job_context"]})
    if not evidence:
        raise HTTPException(status_code=422, detail="Supply at least one authorised candidate, job, application or interview record")
    return evidence, refs


@router.post("/assistant")
async def assistant(
    payload: GenerateInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    role = get_org_role(user_id, payload.organization_id)
    if payload.task not in ALLOWED_TASKS:
        raise HTTPException(status_code=422, detail="Unsupported AI task")
    privileged_tasks = {
        "summarize_candidate", "draft_candidate_message", "extract_job_requirements",
        "draft_job_description", "explain_recommendation", "answer_authorized_records",
    }
    if payload.task in privileged_tasks and role not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Recruiter or organisation administrator permission required for this AI task")
    if payload.task == "interview_questions" and role not in {"owner", "admin", "recruiter", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Interview preparation permission required")
    use_case_key = {
        "summarize_candidate": "recruitment_assistant",
        "extract_job_requirements": "recruitment_assistant",
        "draft_candidate_message": "recruitment_assistant",
        "draft_job_description": "job_description_writer",
        "interview_questions": "interview_preparation",
        "explain_recommendation": "explainable_recommendations",
        "answer_authorized_records": "recruitment_assistant",
    }[payload.task]
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """select id, provider_approved, enabled, approval_status, retention_days
                   from public.ai_use_cases where organization_id=%s and use_case_key=%s""",
                [payload.organization_id, use_case_key],
            )
            use_case = cur.fetchone()
            if not use_case or not use_case["enabled"] or use_case["approval_status"] != "approved" or not use_case["provider_approved"]:
                raise HTTPException(status_code=403, detail="This AI use case is not approved and enabled for this organisation")
            cur.execute(
                """select id, provider, model_name, model_version, prompt_version, limitations
                   from public.ai_model_versions
                   where organization_id=%s and status='approved' and data_processing_approved=true
                   order by approved_at desc nulls last limit 1""",
                [payload.organization_id],
            )
            model = cur.fetchone()
            if not model:
                raise HTTPException(status_code=403, detail="No approved model/provider configuration is available")
            if payload.task == "explain_recommendation" and not payload.recommendation_id:
                raise HTTPException(status_code=422, detail="A recorded recommendation_id is required for a faithful explanation")
            if payload.task in {"draft_job_description", "interview_questions", "extract_job_requirements"} and not payload.job_id:
                raise HTTPException(status_code=422, detail="This task requires a job_id")
            evidence, refs = _load_evidence(cur, payload)
            input_hash = fingerprint({"task": payload.task, "evidence": evidence, "user_request": payload.user_request})
            # Keep raw source inputs out of run history; persist only references and a fingerprint.
            try:
                output_text = generate_text(payload.task, evidence, payload.user_request, model["model_name"], model["provider"])
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except requests_error_types() as exc:
                raise HTTPException(status_code=502, detail="Approved AI provider request failed") from exc
            output = {"text": output_text, "draft_only": payload.task in {"draft_candidate_message", "draft_job_description", "interview_questions"}}
            cur.execute(
                """insert into public.ai_runs
                   (organization_id, use_case_id, model_version_id, actor_user_id, task, status,
                    input_references, input_fingerprint, output, evidence_references, limitations, retention_expires_at)
                   values (%s,%s,%s,%s,%s,'succeeded',%s::jsonb,%s,%s::jsonb,%s::jsonb,%s::jsonb,now()+(%s * interval '1 day'))
                   returning id, task, status, created_at, retention_expires_at""",
                [payload.organization_id, use_case["id"], model["id"], user_id, payload.task,
                 json.dumps(refs), input_hash, json.dumps(output, default=str), json.dumps(refs),
                 json.dumps(model.get("limitations") or []), use_case["retention_days"]],
            )
            run = cur.fetchone()
            if payload.task == "draft_job_description":
                cur.execute(
                    """select coalesce(max(version_number), 0) + 1 as next_version
                       from public.ai_job_description_versions where organization_id=%s and job_id=%s""",
                    [payload.organization_id, payload.job_id],
                )
                version_number = cur.fetchone()["next_version"]
                cur.execute(
                    """insert into public.ai_job_description_versions
                       (organization_id, job_id, version_number, content, source_requirements,
                        quality_findings, ai_run_id, status, created_by)
                       values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,'draft',%s)
                       returning id, version_number, status""",
                    [payload.organization_id, payload.job_id, version_number, output_text,
                     json.dumps(refs), json.dumps(["Human review required; verify salary, benefits, qualifications, working arrangements, clarity and exclusionary wording."]),
                     run["id"], user_id],
                )
                output["draft_record"] = cur.fetchone()
            elif payload.task == "interview_questions":
                cur.execute(
                    """select coalesce(max(version_number), 0) + 1 as next_version
                       from public.ai_interview_kits where organization_id=%s and job_id=%s""",
                    [payload.organization_id, payload.job_id],
                )
                version_number = cur.fetchone()["next_version"]
                cur.execute(
                    """insert into public.ai_interview_kits
                       (organization_id, job_id, job_version_reference, version_number, competencies,
                        questions, ai_run_id, status, created_by)
                       values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,'draft',%s)
                       returning id, version_number, status""",
                    [payload.organization_id, payload.job_id, str(payload.job_id), version_number,
                     json.dumps([]), json.dumps({"draft_text": output_text, "review_required": True}),
                     run["id"], user_id],
                )
                output["draft_record"] = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_generation_completed','ai_run',%s,%s::jsonb)""",
                [payload.organization_id, user_id, run["id"], json.dumps({"task": payload.task, "model_version_id": str(model["id"]),
                 "evidence_reference_count": len(refs), "input_fingerprint": input_hash})],
            )
            return {"run": run, "output": output, "evidence_references": refs,
                    "model": {"provider": model["provider"], "name": model["model_name"],
                              "version": model["model_version"], "prompt_version": model["prompt_version"]},
                    "limitations": model.get("limitations") or [],
                    "human_review_required": True}
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


def requests_error_types():
    import requests
    return (requests.RequestException,)


@router.post("/runs/{run_id}/feedback")
async def feedback(
    run_id: UUID,
    payload: FeedbackInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_runs set feedback_status=%s, feedback_text=%s,
                          status=case when %s='unsafe' then 'reported' else status end,
                          reported_at=case when %s='unsafe' then now() else reported_at end
                   where id=%s and organization_id=%s returning id, status, feedback_status, reported_at""",
                [payload.feedback_status, payload.feedback_text, payload.feedback_status,
                 payload.feedback_status, run_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="AI run not found")
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,%s,'ai_run',%s,%s::jsonb)""",
                [payload.organization_id, user_id,
                 "ai_output_reported" if payload.feedback_status == "unsafe" else "ai_output_feedback",
                 run_id, json.dumps({"feedback_status": payload.feedback_status})],
            )
            if payload.feedback_status == "unsafe":
                cur.execute(
                    """insert into public.ai_incidents
                       (organization_id, ai_run_id, severity, category, description, reported_by)
                       values (%s,%s,'medium','user_report','AI output reported as unsafe',%s)""",
                    [payload.organization_id, run_id, user_id],
                )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/recommendations/{recommendation_id}/review")
async def review_recommendation(
    recommendation_id: UUID,
    payload: ReviewInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if get_org_role(user_id, payload.organization_id) not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Recommendation review permission required")
    if not payload.approved and not (payload.override_reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required when overriding a recommendation")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_recommendations set human_reviewed_by=%s, human_reviewed_at=now(),
                          review_outcome=%s, override_reason=%s
                   where id=%s and organization_id=%s
                   returning id, human_reviewed_by, human_reviewed_at, review_outcome, override_reason""",
                [user_id, "accepted" if payload.approved else "overridden",
                 None if payload.approved else payload.override_reason, recommendation_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_recommendation_reviewed','ai_recommendation',%s,%s::jsonb)""",
                [payload.organization_id, user_id, recommendation_id,
                 json.dumps({"approved": payload.approved, "override_reason": payload.override_reason})],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


class EvaluationInput(BaseModel):
    organization_id: UUID
    model_version_id: UUID
    suite_name: str = Field(min_length=2, max_length=120)
    dataset_version: str = Field(min_length=1, max_length=120)
    pass_criteria: dict = Field(min_length=1)


class EvaluationResultInput(BaseModel):
    test_case_key: str = Field(min_length=1, max_length=160)
    passed: bool
    metric_name: str | None = Field(default=None, max_length=120)
    metric_value: float | None = None
    expected_summary: str | None = Field(default=None, max_length=2000)
    observed_summary: str | None = Field(default=None, max_length=2000)
    details: dict = Field(default_factory=dict)


class EvaluationResultsInput(BaseModel):
    organization_id: UUID
    results: list[EvaluationResultInput] = Field(min_length=1, max_length=500)


class FairnessAuditInput(BaseModel):
    organization_id: UUID
    audit_name: str = Field(min_length=2, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=120)
    methodology: str = Field(min_length=10, max_length=4000)
    outcome_metric: str = Field(min_length=2, max_length=120)
    aggregate_results: dict = Field(min_length=1)
    sample_sizes: dict = Field(min_length=1)
    missingness: dict = Field(default_factory=dict)
    uncertainty_notes: list[str] = Field(default_factory=list, max_length=50)
    legal_review_reference: str = Field(min_length=3, max_length=500)


@router.post("/governance/evaluations", status_code=201)
async def start_evaluation(payload: EvaluationInput, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "select id from public.ai_model_versions where id=%s and organization_id=%s",
                [payload.model_version_id, payload.organization_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Model version not found")
            cur.execute(
                """insert into public.ai_evaluation_runs
                   (organization_id, model_version_id, suite_name, dataset_version, pass_criteria, started_by)
                   values (%s,%s,%s,%s,%s::jsonb,%s)
                   returning id, status, suite_name, dataset_version, pass_criteria, started_at""",
                [payload.organization_id, payload.model_version_id, payload.suite_name,
                 payload.dataset_version, json.dumps(payload.pass_criteria), user_id],
            )
            return cur.fetchone()
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/governance/evaluations/{evaluation_id}/results")
async def complete_evaluation(
    evaluation_id: UUID,
    payload: EvaluationResultsInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """select id, status, pass_criteria from public.ai_evaluation_runs
                   where id=%s and organization_id=%s for update""",
                [evaluation_id, payload.organization_id],
            )
            evaluation = cur.fetchone()
            if not evaluation:
                raise HTTPException(status_code=404, detail="Evaluation run not found")
            if evaluation["status"] != "running":
                raise HTTPException(status_code=409, detail="Evaluation run is already complete")
            criteria = evaluation["pass_criteria"] or {}
            minimum_cases = max(1, int(criteria.get("minimum_cases", 1)))
            max_failure_rate = float(criteria.get("max_failure_rate", 0))
            failed_count = sum(1 for result in payload.results if not result.passed)
            case_count = len(payload.results)
            failure_rate = failed_count / case_count
            passed = case_count >= minimum_cases and failure_rate <= max_failure_rate
            for result in payload.results:
                cur.execute(
                    """insert into public.ai_evaluation_results
                       (organization_id, evaluation_run_id, test_case_key, passed, metric_name,
                        metric_value, expected_summary, observed_summary, details)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    [payload.organization_id, evaluation_id, result.test_case_key, result.passed,
                     result.metric_name, result.metric_value, result.expected_summary,
                     result.observed_summary, json.dumps(result.details)],
                )
            summary = {"case_count": case_count, "failed_count": failed_count,
                       "failure_rate": failure_rate, "minimum_cases": minimum_cases,
                       "max_failure_rate": max_failure_rate}
            cur.execute(
                """update public.ai_evaluation_runs set status=%s, summary=%s::jsonb, completed_at=now()
                   where id=%s and organization_id=%s returning id, status, summary, completed_at""",
                ["passed" if passed else "failed", json.dumps(summary), evaluation_id, payload.organization_id],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_evaluation_completed','ai_evaluation_run',%s,%s::jsonb)""",
                [payload.organization_id, user_id, evaluation_id, json.dumps(summary | {"status": row["status"]})],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/governance/models/{model_id}/approve")
async def approve_model(model_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """select id, data_processing_approved, status from public.ai_model_versions
                   where id=%s and organization_id=%s for update""",
                [model_id, organization_id],
            )
            model = cur.fetchone()
            if not model:
                raise HTTPException(status_code=404, detail="Model version not found")
            if not model["data_processing_approved"]:
                raise HTTPException(status_code=409, detail="Documented provider/data-processing approval is required")
            cur.execute(
                """select id from public.ai_evaluation_runs
                   where organization_id=%s and model_version_id=%s and status='passed'
                   order by completed_at desc limit 1""",
                [organization_id, model_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=409, detail="A passing evaluation run is required before model approval")
            cur.execute(
                """update public.ai_model_versions set status='approved', approved_by=%s, approved_at=now()
                   where id=%s and organization_id=%s
                   returning id, provider, model_name, model_version, status, approved_by, approved_at""",
                [user_id, model_id, organization_id],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_model_approved','ai_model_version',%s,'{}'::jsonb)""",
                [organization_id, user_id, model_id],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/governance/fairness-audits", status_code=201)
async def create_fairness_audit(payload: FairnessAuditInput, user_id: UUID = Depends(get_current_user_id)):
    assert_org_admin(user_id, payload.organization_id)
    # Small groups remain visible to reviewers but must be explicitly flagged as uncertain.
    small_groups = []
    for group, value in payload.sample_sizes.items():
        try:
            if int(value) < 10:
                small_groups.append(str(group))
        except (TypeError, ValueError):
            small_groups.append(str(group))
    notes = list(payload.uncertainty_notes)
    if small_groups:
        notes.append("Small or invalid sample sizes require cautious interpretation: " + ", ".join(small_groups))
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """insert into public.ai_fairness_audits
                   (organization_id, audit_name, dataset_version, methodology, outcome_metric,
                    aggregate_results, sample_sizes, missingness, uncertainty_notes,
                    legal_review_reference)
                   values (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s)
                   returning id, audit_name, dataset_version, outcome_metric, sample_sizes,
                             missingness, uncertainty_notes, legal_review_reference, created_at""",
                [payload.organization_id, payload.audit_name, payload.dataset_version, payload.methodology,
                 payload.outcome_metric, json.dumps(payload.aggregate_results), json.dumps(payload.sample_sizes),
                 json.dumps(payload.missingness), json.dumps(notes), payload.legal_review_reference],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_fairness_audit_created','ai_fairness_audit',%s,%s::jsonb)""",
                [payload.organization_id, user_id, row["id"], json.dumps({"dataset_version": payload.dataset_version,
                 "outcome_metric": payload.outcome_metric, "small_sample_groups": small_groups})],
            )
            return row
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/job-description-versions/{version_id}/review")
async def review_job_description(version_id: UUID, payload: ReviewInput, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    role = get_org_role(user_id, payload.organization_id)
    if role not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Job description review permission required")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_job_description_versions set
                     status=case when %s then 'approved' else 'in_review' end,
                     reviewed_by=%s, reviewed_at=now()
                   where id=%s and organization_id=%s and status in ('draft','in_review')
                   returning id, job_id, version_number, status, reviewed_by, reviewed_at""",
                [payload.approved, user_id, version_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Editable job description draft not found")
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/job-description-versions/{version_id}/publish")
async def publish_job_description(version_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    role = get_org_role(user_id, organization_id)
    if role not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Job description publication permission required")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """select id, job_id, content from public.ai_job_description_versions
                   where id=%s and organization_id=%s and status='approved' for update""",
                [version_id, organization_id],
            )
            draft = cur.fetchone()
            if not draft:
                raise HTTPException(status_code=409, detail="Only an approved draft can be published")
            cur.execute(
                """update public.jobs set description=%s, updated_at=now()
                   where id=%s and organization_id=%s returning id""",
                [draft["content"], draft["job_id"], organization_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Job not found")
            cur.execute(
                """update public.ai_job_description_versions set status='published', published_by=%s, published_at=now()
                   where id=%s and organization_id=%s returning id, job_id, version_number, status, published_at""",
                [user_id, version_id, organization_id],
            )
            row = cur.fetchone()
            cur.execute(
                """update public.ai_job_description_versions set status='superseded'
                   where organization_id=%s and job_id=%s and id<>%s and status='published'""",
                [organization_id, draft["job_id"], version_id],
            )
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_job_description_published','job',%s,%s::jsonb)""",
                [organization_id, user_id, draft["job_id"], json.dumps({"version_id": str(version_id)})],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/interview-kits/{kit_id}/review")
async def review_interview_kit(kit_id: UUID, payload: ReviewInput, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    role = get_org_role(user_id, payload.organization_id)
    if role not in {"owner", "admin", "recruiter", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Interview kit review permission required")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_interview_kits set
                     status=case when %s then 'approved' else 'in_review' end,
                     reviewed_by=%s, reviewed_at=now()
                   where id=%s and organization_id=%s and status in ('draft','in_review')
                   returning id, job_id, version_number, status, reviewed_by, reviewed_at""",
                [payload.approved, user_id, kit_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Interview kit draft not found")
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/recommendations", status_code=201)
async def create_recorded_recommendation(
    payload: RecommendationInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if get_org_role(user_id, payload.organization_id) not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Recommendation recording permission required")
    table_by_type = {
        "candidate": "candidates",
        "application": "applications",
        "job": "jobs",
        "interview": "interviews",
        "job_description": "ai_job_description_versions",
    }
    table = table_by_type[payload.object_type]
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"select id from public.{table} where id=%s and organization_id=%s",
                [payload.object_id, payload.organization_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Recommendation target not found")
            cur.execute(
                """select id from public.ai_model_versions
                   where id=%s and organization_id=%s and status='approved' and data_processing_approved=true""",
                [payload.model_version_id, payload.organization_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=409, detail="An approved model version with data-processing approval is required")
            cur.execute(
                """insert into public.ai_recommendations
                   (organization_id, object_type, object_id, purpose, input_references, evidence,
                    explanation, limitations, model_version_id)
                   values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s)
                   returning id, object_type, object_id, purpose, input_references, evidence,
                             explanation, limitations, model_version_id, created_at""",
                [payload.organization_id, payload.object_type, payload.object_id, payload.purpose,
                 json.dumps(payload.input_references), json.dumps(payload.evidence), payload.explanation,
                 json.dumps(payload.limitations), payload.model_version_id],
            )
            row = cur.fetchone()
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_recommendation_recorded','ai_recommendation',%s,%s::jsonb)""",
                [payload.organization_id, user_id, row["id"], json.dumps({"object_type": payload.object_type,
                 "object_id": str(payload.object_id), "purpose": payload.purpose})],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


class DraftEditInput(BaseModel):
    organization_id: UUID
    content: str = Field(min_length=1, max_length=20000)


class IncidentUpdateInput(BaseModel):
    organization_id: UUID
    status: Literal["open", "investigating", "mitigated", "closed"]
    remediation: str | None = Field(default=None, max_length=6000)


@router.patch("/governance/incidents/{incident_id}")
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdateInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_admin(user_id, payload.organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_incidents set status=%s, remediation=%s,
                          resolved_at=case when %s in ('mitigated','closed') then now() else null end
                   where id=%s and organization_id=%s
                   returning id, severity, category, status, remediation, resolved_at""",
                [payload.status, payload.remediation, payload.status, incident_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="AI incident not found")
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'ai_incident_updated','ai_incident',%s,%s::jsonb)""",
                [payload.organization_id, user_id, incident_id,
                 json.dumps({"status": payload.status, "remediation_recorded": bool(payload.remediation)})],
            )
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.post("/governance/retention-cleanup")
async def cleanup_expired_ai_runs(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    """Admin-triggered cleanup. Production must schedule this endpoint or equivalent trusted job."""
    assert_org_admin(user_id, organization_id)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """delete from public.ai_runs where organization_id=%s and retention_expires_at <= now()
                   returning id""",
                [organization_id],
            )
            deleted_ids = [str(row["id"]) for row in cur.fetchall()]
            cur.execute(
                """insert into public.audit_events (organization_id, actor_user_id, action, entity_type, metadata)
                   values (%s,%s,'ai_retention_cleanup','ai_run',%s::jsonb)""",
                [organization_id, user_id, json.dumps({"deleted_count": len(deleted_ids)})],
            )
            return {"deleted_count": len(deleted_ids), "cleanup_at": datetime.now(timezone.utc)}
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.put("/job-description-versions/{version_id}")
async def edit_job_description_draft(
    version_id: UUID,
    payload: DraftEditInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if get_org_role(user_id, payload.organization_id) not in {"owner", "admin", "recruiter"}:
        raise HTTPException(status_code=403, detail="Job description editing permission required")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_job_description_versions set content=%s
                   where id=%s and organization_id=%s and status in ('draft','in_review')
                   returning id, job_id, version_number, status, content""",
                [payload.content, version_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=409, detail="Only an editable draft can be changed")
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc


@router.put("/interview-kits/{kit_id}")
async def edit_interview_kit_draft(
    kit_id: UUID,
    payload: DraftEditInput,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, payload.organization_id)
    if get_org_role(user_id, payload.organization_id) not in {"owner", "admin", "recruiter", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Interview kit editing permission required")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """update public.ai_interview_kits set questions=%s::jsonb
                   where id=%s and organization_id=%s and status in ('draft','in_review')
                   returning id, job_id, version_number, status, questions""",
                [json.dumps({"draft_text": payload.content, "review_required": True}),
                 kit_id, payload.organization_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=409, detail="Only an editable interview kit draft can be changed")
            return row
    except HTTPException:
        raise
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _db_error(exc) from exc
