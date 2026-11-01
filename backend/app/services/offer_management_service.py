import hashlib
import json
from uuid import UUID

from fastapi import HTTPException

from app.db import get_connection
from app.schemas.offer_management import OfferApprovalDecision, OfferCandidateResponse


TERMINAL_STATES = {"accepted", "declined", "expired", "withdrawn", "rejected"}


def _terms(row: dict) -> dict:
    keys = (
        "application_id", "title", "employment_type", "start_date", "salary_amount",
        "salary_currency", "bonus_amount", "benefits", "expires_at", "notes",
    )
    return {key: row.get(key) for key in keys}


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):  # Decimal
        return str(value)
    raise TypeError(f"Unsupported offer term value: {type(value).__name__}")


def _save_version(cur, organization_id: UUID, offer_id: UUID, row: dict, actor_id: UUID, version_number: int):
    terms = _terms(row)
    serialized = json.dumps(terms, sort_keys=True, separators=(",", ":"), default=_json_value)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    cur.execute(
        """insert into public.offer_versions
           (organization_id, offer_id, version_number, terms, terms_sha256, created_by)
           values (%s,%s,%s,%s::jsonb,%s,%s)
           returning *""",
        [organization_id, offer_id, version_number, serialized, digest, actor_id],
    )
    return cur.fetchone()


def submit_for_approval(organization_id: UUID, offer_id: UUID, actor_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s for update",
                [offer_id, organization_id],
            )
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] != "draft":
                raise HTTPException(409, "Only draft offers can be submitted for approval")
            version = offer.get("current_version") or 1
            cur.execute(
                "select id from public.offer_versions where organization_id=%s and offer_id=%s and version_number=%s",
                [organization_id, offer_id, version],
            )
            if cur.fetchone() is None:
                _save_version(cur, organization_id, offer_id, offer, actor_id, version)
            cur.execute(
                "update public.offers set status='awaiting_approval', updated_at=now() where id=%s and organization_id=%s returning *",
                [offer_id, organization_id],
            )
            result = cur.fetchone()
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'offer_submitted_for_approval','offer',%s,%s::jsonb)""",
                [organization_id, actor_id, offer_id, json.dumps({"version": version})],
            )
        conn.commit()
        return result


def decide_approval(organization_id: UUID, offer_id: UUID, actor_id: UUID, payload: OfferApprovalDecision):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s for update",
                [offer_id, organization_id],
            )
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] != "awaiting_approval":
                raise HTTPException(409, "Offer is not awaiting approval")
            version = offer.get("current_version") or 1
            cur.execute(
                "select id from public.offer_versions where organization_id=%s and offer_id=%s and version_number=%s",
                [organization_id, offer_id, version],
            )
            version_row = cur.fetchone()
            if not version_row:
                raise HTTPException(409, "Offer version snapshot is missing")
            cur.execute(
                """insert into public.offer_approvals
                   (organization_id, offer_id, offer_version_id, approver_id, decision, comments)
                   values (%s,%s,%s,%s,%s,%s) returning *""",
                [organization_id, offer_id, version_row["id"], actor_id, payload.decision, payload.comments],
            )
            approval = cur.fetchone()
            next_status = "approved" if payload.decision == "approved" else "draft"
            cur.execute(
                """update public.offers
                   set status=%s, approved_by=case when %s='approved' then %s else null end,
                       approved_at=case when %s='approved' then now() else null end,
                       updated_at=now()
                   where id=%s and organization_id=%s returning *""",
                [next_status, payload.decision, actor_id, payload.decision, offer_id, organization_id],
            )
            result = cur.fetchone()
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,%s,'offer',%s,%s::jsonb)""",
                [organization_id, actor_id, "offer_approval_" + payload.decision, offer_id,
                 json.dumps({"version": version, "approval_id": str(approval["id"])})],
            )
        conn.commit()
        return {"offer": result, "approval": approval}


def issue_offer(organization_id: UUID, offer_id: UUID, actor_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s for update",
                [offer_id, organization_id],
            )
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] != "approved":
                raise HTTPException(409, "Only approved offers can be issued")
            version = offer.get("current_version") or 1
            cur.execute(
                """select id, terms, terms_sha256 from public.offer_versions
                   where organization_id=%s and offer_id=%s and version_number=%s""",
                [organization_id, offer_id, version],
            )
            snapshot = cur.fetchone()
            if not snapshot:
                raise HTTPException(409, "Approved offer version snapshot is missing")
            # The version row is immutable. Issuance metadata belongs to the offer lifecycle row.
            cur.execute(
                """update public.offers set status='issued', issued_at=now(), issued_by=%s,
                   sent_at=now(), updated_at=now()
                   where id=%s and organization_id=%s returning *""",
                [actor_id, offer_id, organization_id],
            )
            result = cur.fetchone()
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'offer_issued','offer',%s,%s::jsonb)""",
                [organization_id, actor_id, offer_id,
                 json.dumps({"version": version, "version_id": str(snapshot["id"]), "terms_sha256": snapshot["terms_sha256"]})],
            )
        conn.commit()
        return result


def record_candidate_response(organization_id: UUID, offer_id: UUID, actor_id: UUID, payload: OfferCandidateResponse):
    # This staff-recorded workflow requires a source reference. It is not a candidate portal
    # and must not be represented as authenticated self-service acceptance.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.offers where id=%s and organization_id=%s for update",
                [offer_id, organization_id],
            )
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] != "issued":
                raise HTTPException(409, "Only issued offers can receive a candidate response")
            cur.execute(
                """update public.offers set status=%s, candidate_response=%s,
                   candidate_responded_at=now(), responded_at=now(), updated_at=now()
                   where id=%s and organization_id=%s returning *""",
                [payload.response, payload.response, offer_id, organization_id],
            )
            result = cur.fetchone()
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,%s,'offer',%s,%s::jsonb)""",
                [organization_id, actor_id, "candidate_offer_" + payload.response, offer_id,
                 json.dumps({"evidence_reference": payload.evidence_reference, "recorded_by_staff": True})],
            )
        conn.commit()
        return result


def list_versions(organization_id: UUID, offer_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1 from public.offers where id=%s and organization_id=%s", [offer_id, organization_id])
            if cur.fetchone() is None:
                raise HTTPException(404, "Offer not found")
            cur.execute(
                """select * from public.offer_versions where organization_id=%s and offer_id=%s
                   order by version_number desc""",
                [organization_id, offer_id],
            )
            return cur.fetchall()


def list_approvals(organization_id: UUID, offer_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1 from public.offers where id=%s and organization_id=%s", [offer_id, organization_id])
            if cur.fetchone() is None:
                raise HTTPException(404, "Offer not found")
            cur.execute(
                """select * from public.offer_approvals where organization_id=%s and offer_id=%s
                   order by decided_at desc""",
                [organization_id, offer_id],
            )
            return cur.fetchall()


def withdraw_offer(organization_id: UUID, offer_id: UUID, actor_id: UUID, reason: str):
    reason = reason.strip()
    if not reason or len(reason) > 2000:
        raise HTTPException(422, "A withdrawal reason of 1 to 2000 characters is required")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select status from public.offers where id=%s and organization_id=%s for update", [offer_id, organization_id])
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] not in {"draft", "awaiting_approval", "approved", "issued"}:
                raise HTTPException(409, "This offer can no longer be withdrawn")
            cur.execute(
                """update public.offers set status='withdrawn', withdrawn_at=now(), withdrawn_by=%s,
                   responded_at=now(), updated_at=now()
                   where id=%s and organization_id=%s returning *""",
                [actor_id, offer_id, organization_id],
            )
            result = cur.fetchone()
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'offer_withdrawn','offer',%s,%s::jsonb)""",
                [organization_id, actor_id, offer_id, json.dumps({"reason": reason})],
            )
        conn.commit()
        return result


def expire_offer(organization_id: UUID, offer_id: UUID, actor_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select status, expires_at from public.offers where id=%s and organization_id=%s for update", [offer_id, organization_id])
            offer = cur.fetchone()
            if not offer:
                raise HTTPException(404, "Offer not found")
            if offer["status"] != "issued":
                raise HTTPException(409, "Only issued offers can expire")
            if offer["expires_at"] is None:
                raise HTTPException(409, "This offer has no expiry date")
            cur.execute(
                """update public.offers set status='expired', responded_at=now(), updated_at=now()
                   where id=%s and organization_id=%s and expires_at <= now() returning *""",
                [offer_id, organization_id],
            )
            result = cur.fetchone()
            if result is None:
                raise HTTPException(409, "Offer expiry date is still in the future")
            cur.execute(
                """insert into public.audit_events
                   (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
                   values (%s,%s,'offer_expired','offer',%s,'{}'::jsonb)""",
                [organization_id, actor_id, offer_id],
            )
        conn.commit()
        return result
