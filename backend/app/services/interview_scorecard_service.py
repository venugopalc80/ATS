"""Tenant-scoped persistence for interview kits and evidence-based scorecards."""
import json
from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.interview_scorecards import InterviewKitDefinition, InterviewFeedbackDraft


def _insert_template(cursor: Any, organization_id: UUID, kit_id: UUID, user_id: UUID,
                     definition: InterviewKitDefinition, version_number: int) -> dict[str, Any]:
    cursor.execute(
        """insert into public.scorecard_templates
             (organization_id, kit_id, version_number, instructions, created_by)
           values (%s,%s,%s,%s,%s)
           returning id, organization_id, kit_id, version_number, instructions, status, created_at""",
        [organization_id, kit_id, version_number, definition.instructions, user_id],
    )
    template = cursor.fetchone()
    for position, competency in enumerate(definition.competencies):
        cursor.execute(
            """insert into public.competencies
                 (organization_id, template_id, competency_key, name, description, rating_guidance, display_order)
               values (%s,%s,%s,%s,%s,%s::jsonb,%s) returning id""",
            [organization_id, template["id"], competency.key, competency.name, competency.description,
             json.dumps(competency.rating_guidance), position],
        )
        competency_id = cursor.fetchone()["id"]
        for question_position, question in enumerate(competency.questions):
            cursor.execute(
                """insert into public.interview_kit_questions
                     (organization_id, template_id, competency_id, question, evaluation_guidance, display_order)
                   values (%s,%s,%s,%s,%s,%s)""",
                [organization_id, template["id"], competency_id, question.question,
                 question.evaluation_guidance, question_position],
            )
    return template


def _definition_from_payload(payload: InterviewKitDefinition) -> InterviewKitDefinition:
    return payload


def list_kits(organization_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select k.id, k.organization_id, k.job_id, k.name, k.description, k.status,
                          k.current_version_id, k.created_by, k.updated_at,
                          t.version_number, t.instructions, t.published_at,
                          draft.id as draft_template_id
                   from public.interview_kits k
                   left join public.scorecard_templates t
                     on t.organization_id=k.organization_id and t.id=k.current_version_id
                   left join lateral (
                     select id from public.scorecard_templates d
                     where d.organization_id=k.organization_id and d.kit_id=k.id and d.status='draft'
                     order by d.version_number desc limit 1
                   ) draft on true
                   where k.organization_id=%s and k.status <> 'archived'
                   order by k.updated_at desc""",
                [organization_id],
            )
            return list(cursor.fetchall())


def create_kit(organization_id: UUID, user_id: UUID, job_id: UUID | None,
               definition: InterviewKitDefinition) -> dict[str, Any]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if job_id is not None:
                cursor.execute("select 1 from public.jobs where id=%s and organization_id=%s", [job_id, organization_id])
                if cursor.fetchone() is None:
                    raise ValueError("The selected job does not belong to this organization")
            cursor.execute(
                """insert into public.interview_kits
                     (organization_id, job_id, name, description, created_by, updated_by)
                   values (%s,%s,%s,%s,%s,%s)
                   returning id, organization_id, job_id, name, description, status, created_at, updated_at""",
                [organization_id, job_id, definition.name, definition.description, user_id, user_id],
            )
            kit = cursor.fetchone()
            template = _insert_template(cursor, organization_id, kit["id"], user_id, definition, 1)
            kit["draft_template_id"] = template["id"]
            return kit


def create_version(organization_id: UUID, kit_id: UUID, user_id: UUID,
                   definition: InterviewKitDefinition) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select id, status from public.interview_kits
                   where organization_id=%s and id=%s for update""",
                [organization_id, kit_id],
            )
            kit = cursor.fetchone()
            if kit is None or kit["status"] == "archived":
                return None
            cursor.execute(
                "select coalesce(max(version_number),0)+1 as next_version from public.scorecard_templates where organization_id=%s and kit_id=%s",
                [organization_id, kit_id],
            )
            version = int(cursor.fetchone()["next_version"])
            cursor.execute(
                """update public.interview_kits set name=%s, description=%s, updated_by=%s, updated_at=now()
                   where organization_id=%s and id=%s""",
                [definition.name, definition.description, user_id, organization_id, kit_id],
            )
            template = _insert_template(cursor, organization_id, kit_id, user_id, definition, version)
            return {"kit_id": kit_id, **template}


def publish_kit(organization_id: UUID, kit_id: UUID, template_id: UUID, user_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select t.id, t.version_number, t.status
                   from public.scorecard_templates t
                   join public.interview_kits k
                     on k.organization_id=t.organization_id and k.id=t.kit_id
                   where t.organization_id=%s and k.id=%s and t.id=%s
                   for update of t, k""",
                [organization_id, kit_id, template_id],
            )
            template = cursor.fetchone()
            if template is None:
                return None
            if template["status"] == "published":
                return {"kit_id": kit_id, **template}
            cursor.execute("select count(*) as n from public.competencies where organization_id=%s and template_id=%s",
                           [organization_id, template_id])
            if int(cursor.fetchone()["n"]) < 1:
                raise ValueError("A scorecard needs at least one competency")
            cursor.execute(
                """update public.scorecard_templates set status='published', published_at=now()
                   where organization_id=%s and id=%s
                   returning id, version_number, status, published_at""",
                [organization_id, template_id],
            )
            published = cursor.fetchone()
            cursor.execute(
                """update public.interview_kits set status='published', current_version_id=%s,
                          updated_by=%s, updated_at=now()
                   where organization_id=%s and id=%s""",
                [template_id, user_id, organization_id, kit_id],
            )
            cursor.execute(
                """insert into public.audit_events
                     (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'interview_kit.published','interview_kit',%s,%s::jsonb)""",
                [organization_id, user_id, kit_id, json.dumps({"template_id": str(template_id),
                                                               "version_number": published["version_number"]})],
            )
            return {"kit_id": kit_id, **published}


def get_template_for_interview(organization_id: UUID, interview_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select i.id as interview_id, i.application_id, i.interviewer_ids, a.job_id
                   from public.interviews i
                   join public.applications a on a.id=i.application_id
                   where i.organization_id=%s and i.id=%s""",
                [organization_id, interview_id],
            )
            interview = cursor.fetchone()
            if interview is None:
                return None
            cursor.execute(
                """select k.id as kit_id, k.name, k.description, t.id as template_id,
                          t.version_number, t.instructions
                   from public.interview_kits k
                   join public.scorecard_templates t
                     on t.organization_id=k.organization_id and t.id=k.current_version_id
                   where k.organization_id=%s and k.status='published'
                     and (k.job_id is null or k.job_id=%s)
                   order by (k.job_id is not null) desc, k.updated_at desc limit 1""",
                [organization_id, interview["job_id"]],
            )
            template = cursor.fetchone()
            if template is None:
                return {"interview_id": interview_id, "application_id": interview["application_id"],
                        "interviewer_ids": interview["interviewer_ids"], "template": None}
            cursor.execute(
                """select id, competency_key, name, description, rating_guidance, display_order
                   from public.competencies where organization_id=%s and template_id=%s
                   order by display_order, name""",
                [organization_id, template["template_id"]],
            )
            competencies = list(cursor.fetchall())
            for competency in competencies:
                cursor.execute(
                    """select id, question, evaluation_guidance, display_order
                       from public.interview_kit_questions
                       where organization_id=%s and template_id=%s and competency_id=%s
                       order by display_order""",
                    [organization_id, template["template_id"], competency["id"]],
                )
                competency["questions"] = list(cursor.fetchall())
            return {"interview_id": interview_id, "application_id": interview["application_id"],
                    "interviewer_ids": interview["interviewer_ids"], "template": template,
                    "competencies": competencies}


def save_feedback(organization_id: UUID, interview_id: UUID, user_id: UUID,
                  payload: InterviewFeedbackDraft, submit: bool = False) -> dict[str, Any]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select i.id, i.application_id, i.interviewer_ids, i.status as interview_status, a.job_id
                   from public.interviews i
                   join public.applications a on a.id=i.application_id
                   where i.organization_id=%s and i.id=%s for update of i""",
                [organization_id, interview_id],
            )
            interview = cursor.fetchone()
            if interview is None:
                raise LookupError("Interview not found")
            if user_id not in {UUID(str(value)) for value in (interview["interviewer_ids"] or [])}:
                raise PermissionError("Only an assigned interviewer can submit this scorecard")
            if submit and interview["interview_status"] != "completed":
                raise ValueError("Complete the interview before submitting the scorecard")
            cursor.execute(
                """select t.id, t.kit_id from public.scorecard_templates t
                   join public.interview_kits k on k.organization_id=t.organization_id and k.id=t.kit_id
                   where t.organization_id=%s and t.id=%s and t.status='published'
                     and (k.job_id is null or k.job_id=%s)""",
                [organization_id, payload.template_id, interview["job_id"]],
            )
            template = cursor.fetchone()
            if template is None:
                raise ValueError("Published scorecard template does not match this interview's job")
            cursor.execute(
                """select id, status, template_id from public.interview_feedback
                   where organization_id=%s and interview_id=%s and interviewer_id=%s for update""",
                [organization_id, interview_id, user_id],
            )
            feedback = cursor.fetchone()
            if feedback and feedback["status"] == "submitted":
                raise ValueError("Submitted feedback is locked and cannot be edited")
            if feedback and str(feedback["template_id"]) != str(payload.template_id):
                raise ValueError("A draft must use the same template version it was created with")
            cursor.execute(
                "select id from public.competencies where organization_id=%s and template_id=%s",
                [organization_id, payload.template_id],
            )
            expected = {UUID(str(row["id"])) for row in cursor.fetchall()}
            provided = {item.competency_id for item in payload.responses}
            if not provided.issubset(expected):
                raise ValueError("Responses must reference competencies from the selected template")
            if submit and provided != expected:
                raise ValueError("Complete every competency before submitting feedback")
            if submit and any(not item.evidence.strip() for item in payload.responses):
                raise ValueError("Every competency needs specific supporting evidence before submission")
            if feedback is None:
                cursor.execute(
                    """insert into public.interview_feedback
                         (organization_id, interview_id, application_id, interviewer_id, template_id,
                          overall_summary, strengths, concerns)
                       values (%s,%s,%s,%s,%s,%s,%s,%s)
                       returning id, status, submitted_at""",
                    [organization_id, interview_id, interview["application_id"], user_id, payload.template_id,
                     payload.overall_summary, payload.strengths, payload.concerns],
                )
                feedback = cursor.fetchone()
            else:
                cursor.execute(
                    """update public.interview_feedback set overall_summary=%s, strengths=%s, concerns=%s,
                              updated_at=now()
                       where organization_id=%s and id=%s returning id, status, submitted_at""",
                    [payload.overall_summary, payload.strengths, payload.concerns, organization_id, feedback["id"]],
                )
                feedback = cursor.fetchone()
            cursor.execute("delete from public.scorecard_responses where organization_id=%s and feedback_id=%s",
                           [organization_id, feedback["id"]])
            for item in payload.responses:
                cursor.execute(
                    """insert into public.scorecard_responses
                         (organization_id, feedback_id, competency_id, rating, evidence, notes)
                       values (%s,%s,%s,%s,%s,%s)""",
                    [organization_id, feedback["id"], item.competency_id, item.rating, item.evidence, item.notes],
                )
            if submit:
                cursor.execute(
                    """update public.interview_feedback set status='submitted', submitted_at=now(), updated_at=now()
                       where organization_id=%s and id=%s returning id, status, submitted_at""",
                    [organization_id, feedback["id"]],
                )
                feedback = cursor.fetchone()
                cursor.execute(
                    """insert into public.audit_events
                         (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                       values (%s,%s,'interview_scorecard.submitted','interview_feedback',%s,%s::jsonb)""",
                    [organization_id, user_id, feedback["id"],
                     json.dumps({"interview_id": str(interview_id), "template_id": str(payload.template_id),
                                 "response_count": len(payload.responses)})],
                )
            return {"id": feedback["id"], "interview_id": interview_id, "template_id": payload.template_id,
                    "status": feedback["status"], "submitted_at": feedback["submitted_at"]}


def review_feedback(organization_id: UUID, interview_id: UUID, user_id: UUID, can_review_early: bool = False) -> dict[str, Any]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select interviewer_ids from public.interviews
                   where organization_id=%s and id=%s""",
                [organization_id, interview_id],
            )
            interview = cursor.fetchone()
            if interview is None:
                raise LookupError("Interview not found")
            assigned = [UUID(str(value)) for value in (interview["interviewer_ids"] or [])]
            if user_id not in assigned and not can_review_early:
                raise PermissionError("Only assigned interviewers or authorised reviewers can review scorecards")
            if user_id in assigned:
                cursor.execute(
                    """select status from public.interview_feedback
                       where organization_id=%s and interview_id=%s and interviewer_id=%s""",
                    [organization_id, interview_id, user_id],
                )
                own = cursor.fetchone()
                if own is None or own["status"] != "submitted":
                    raise PermissionError("Submit your own scorecard before viewing other interviewers' feedback")
            cursor.execute(
                """select f.id, f.interviewer_id, f.template_id, f.status, f.overall_summary,
                          f.strengths, f.concerns, f.submitted_at, r.id as response_id, r.competency_id, r.rating,
                          r.evidence, r.notes, c.name as competency_name, c.competency_key
                   from public.interview_feedback f
                   left join public.scorecard_responses r
                     on r.organization_id=f.organization_id and r.feedback_id=f.id
                   left join public.competencies c
                     on c.organization_id=r.organization_id and c.id=r.competency_id
                   where f.organization_id=%s and f.interview_id=%s and f.status='submitted'
                   order by f.submitted_at, f.interviewer_id, c.display_order""",
                [organization_id, interview_id],
            )
            rows = list(cursor.fetchall())
            cursor.execute(
                """select count(*) as total from public.interview_feedback
                   where organization_id=%s and interview_id=%s and status='submitted'""",
                [organization_id, interview_id],
            )
            submitted = int(cursor.fetchone()["total"])
            missing = [str(value) for value in assigned if not any(
                str(row["interviewer_id"]) == str(value) and row["status"] == "submitted" for row in rows
            )]
            cursor.execute(
                """select id, reviewer_id, decision, rationale, evidence_snapshot, created_at
                   from public.interview_scorecard_decisions
                   where organization_id=%s and interview_id=%s
                   order by created_at desc""",
                [organization_id, interview_id],
            )
            decisions = list(cursor.fetchall())
            return {"interview_id": interview_id, "assigned_interviewer_count": len(assigned),
                    "submitted_feedback_count": submitted, "missing_interviewer_ids": missing,
                    "feedback": rows, "decisions": decisions,
                    "note": "Ratings are evidence summaries, not an automated hiring decision."}


def get_my_feedback(organization_id: UUID, interview_id: UUID, user_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select interviewer_ids from public.interviews
                   where organization_id=%s and id=%s""",
                [organization_id, interview_id],
            )
            interview = cursor.fetchone()
            if interview is None:
                return None
            if user_id not in {UUID(str(value)) for value in (interview["interviewer_ids"] or [])}:
                raise PermissionError("Only an assigned interviewer can access their own scorecard")
            cursor.execute(
                """select id, template_id, status, overall_summary, strengths, concerns, submitted_at
                   from public.interview_feedback
                   where organization_id=%s and interview_id=%s and interviewer_id=%s""",
                [organization_id, interview_id, user_id],
            )
            feedback = cursor.fetchone()
            if feedback is None:
                return None
            cursor.execute(
                """select competency_id, rating, evidence, notes
                   from public.scorecard_responses
                   where organization_id=%s and feedback_id=%s""",
                [organization_id, feedback["id"]],
            )
            feedback["responses"] = list(cursor.fetchall())
            return feedback


def record_decision(organization_id: UUID, interview_id: UUID, reviewer_id: UUID,
                    decision: str, rationale: str, evidence_response_ids: list[UUID]) -> dict[str, Any]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select interviewer_ids from public.interviews
                   where organization_id=%s and id=%s""",
                [organization_id, interview_id],
            )
            interview = cursor.fetchone()
            if interview is None:
                raise LookupError("Interview not found")
            assigned = {UUID(str(value)) for value in (interview["interviewer_ids"] or [])}
            cursor.execute(
                """select interviewer_id from public.interview_feedback
                   where organization_id=%s and interview_id=%s and status='submitted'""",
                [organization_id, interview_id],
            )
            submitted = {UUID(str(row["interviewer_id"])) for row in cursor.fetchall()}
            if not assigned or not assigned.issubset(submitted):
                raise ValueError("All assigned interviewers must submit feedback before a final review decision")
            cursor.execute(
                """select r.id, r.competency_id, c.name as competency_name, r.rating, r.evidence,
                          r.notes, f.interviewer_id, f.template_id, f.submitted_at
                   from public.scorecard_responses r
                   join public.interview_feedback f
                     on f.organization_id=r.organization_id and f.id=r.feedback_id
                   join public.competencies c
                     on c.organization_id=r.organization_id and c.id=r.competency_id
                   where r.organization_id=%s and f.interview_id=%s and f.status='submitted'
                     and r.id = any(%s)""",
                [organization_id, interview_id, evidence_response_ids],
            )
            evidence = list(cursor.fetchall())
            if len(evidence) != len(evidence_response_ids):
                raise ValueError("Every cited evidence item must belong to a submitted scorecard for this interview")
            snapshot = [{
                "response_id": str(row["id"]),
                "competency_id": str(row["competency_id"]),
                "competency": row["competency_name"],
                "rating": row["rating"],
                "evidence": row["evidence"],
                "notes": row["notes"],
                "interviewer_id": str(row["interviewer_id"]),
                "template_id": str(row["template_id"]),
                "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
            } for row in evidence]
            cursor.execute(
                """insert into public.interview_scorecard_decisions
                     (organization_id, interview_id, reviewer_id, decision, rationale, evidence_snapshot)
                   values (%s,%s,%s,%s,%s,%s::jsonb)
                   returning id, organization_id, interview_id, reviewer_id, decision, rationale,
                             evidence_snapshot, created_at""",
                [organization_id, interview_id, reviewer_id, decision, rationale, json.dumps(snapshot)],
            )
            result = cursor.fetchone()
            cursor.execute(
                """insert into public.audit_events
                     (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'interview_scorecard.decision_recorded','interview_scorecard_decision',%s,%s::jsonb)""",
                [organization_id, reviewer_id, result["id"],
                 json.dumps({"interview_id": str(interview_id), "decision": decision,
                             "evidence_count": len(snapshot)})],
            )
            return result
