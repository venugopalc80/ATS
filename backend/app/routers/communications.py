from datetime import datetime, timezone
import os
from uuid import UUID

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import assert_org_permission, get_current_user_id
from app.db import get_connection
from app.services.candidate_service import CandidateService

router = APIRouter(prefix="/api/candidates", tags=["candidate communications"])
candidate_service = CandidateService()

EMAIL_TEMPLATES = [
    {"key": "introduction", "name": "Recruiter introduction", "subject": "Introduction from {recruiter_name}", "body": "Hi {candidate_name},\n\nI hope you are well. My name is {recruiter_name}, and I work with {agency_name}. I would be pleased to learn more about your career interests and discuss how I may be able to support your next move.\n\nWould you be open to a brief conversation?\n\nKind regards,\n{recruiter_name}"},
    {"key": "job_share", "name": "Share a job opportunity", "subject": "An opportunity that may interest you: {job_title}", "body": "Hi {candidate_name},\n\nI am reaching out because I thought this opportunity may be relevant to your experience.\n\nRole: {job_title}\nCompany: {company_name}\n\nIf you would like to hear more, reply to this email and I can share the full details.\n\nKind regards,\n{recruiter_name}"},
    {"key": "outreach", "name": "Candidate outreach", "subject": "Exploring your next career opportunity", "body": "Hi {candidate_name},\n\nI came across your profile and wanted to ask whether you are open to hearing about relevant opportunities. Your experience as {current_title} caught my attention.\n\nIf you are open to a conversation, please let me know a convenient time.\n\nKind regards,\n{recruiter_name}"},
    {"key": "interview_invitation", "name": "Interview invitation", "subject": "Interview invitation: {job_title}", "body": "Hi {candidate_name},\n\nWe would like to invite you to an interview for {job_title}.\n\nProposed date and time: {interview_datetime}\nLocation or meeting link: {meeting_link}\n\nPlease reply to confirm whether this works for you.\n\nKind regards,\n{recruiter_name}"},
    {"key": "interview_confirmation", "name": "Interview confirmation", "subject": "Interview confirmed: {job_title}", "body": "Hi {candidate_name},\n\nYour interview for {job_title} is confirmed.\n\nDate and time: {interview_datetime}\nLocation or meeting link: {meeting_link}\n\nPlease let me know if you have any questions before the interview.\n\nKind regards,\n{recruiter_name}"},
    {"key": "follow_up", "name": "Follow-up", "subject": "Following up: {job_title}", "body": "Hi {candidate_name},\n\nI wanted to follow up on my previous message about {job_title}. Please let me know if you would like to discuss this opportunity or if the timing is not right.\n\nKind regards,\n{recruiter_name}"},
    {"key": "cv_request", "name": "Request an updated CV", "subject": "Updated CV request", "body": "Hi {candidate_name},\n\nCould you please share your latest CV when convenient? This will help us ensure your experience and recent work are represented accurately.\n\nKind regards,\n{recruiter_name}"},
]

class CandidateEmailSend(BaseModel):
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=20000)
    template_key: str | None = Field(default=None, max_length=80)

@router.get("/communications/templates")
async def list_candidate_email_templates(
    user_id: UUID = Depends(get_current_user_id),
):
    # Template definitions contain no tenant data. Candidate-level permission is
    # checked again on send, where the organisation and candidate are known.
    return {"templates": EMAIL_TEMPLATES}

@router.get("/{candidate_id}/communications")
async def list_candidate_communications(
    candidate_id: UUID,
    organization_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    candidate = await candidate_service.get_candidate(candidate_id)
    if candidate is None or str(candidate["organization_id"]) != str(organization_id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    assert_org_permission(user_id, organization_id, "candidates.communicate")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select id, channel, direction, subject, body_text, recipient_email,
                       sender_user_id, provider, provider_message_id, delivery_status,
                       template_key, created_at
                from public.candidate_communications
                where organization_id=%s and candidate_id=%s
                order by created_at desc
                limit 100
                """,
                [organization_id, candidate_id],
            )
            rows = list(cursor.fetchall())
    return rows

@router.post("/{candidate_id}/communications/email", status_code=201)
async def send_candidate_email(
    candidate_id: UUID,
    organization_id: UUID,
    payload: CandidateEmailSend,
    user_id: UUID = Depends(get_current_user_id),
):
    candidate = await candidate_service.get_candidate(candidate_id)
    if candidate is None or str(candidate["organization_id"]) != str(organization_id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    assert_org_permission(user_id, organization_id, "candidates.communicate")
    if candidate.get("status") == "do_not_contact":
        raise HTTPException(status_code=409, detail="This candidate is marked Do not contact. Change the candidate's contact status only after verifying the appropriate permission and lawful basis.")
    recipient = (candidate.get("email") or "").strip()
    if not recipient:
        raise HTTPException(status_code=422, detail="This candidate does not have an email address.")

    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL")
    if not api_key or not from_email:
        raise HTTPException(status_code=503, detail="Email sending is not configured. Set RESEND_API_KEY and RESEND_FROM_EMAIL on the staging API.")

    response = None
    provider_id = None
    delivery_status = "failed"
    error_detail = None
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [recipient],
                "subject": payload.subject.strip(),
                "text": payload.body,
            },
            timeout=20,
        )
        if response.ok:
            provider_payload = response.json()
            provider_id = provider_payload.get("id")
            delivery_status = "sent"
        else:
            error_detail = f"Email provider returned HTTP {response.status_code}"
    except requests.RequestException:
        error_detail = "Email provider could not be reached"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.candidate_communications
                  (organization_id, candidate_id, channel, direction, subject, body_text,
                   recipient_email, sender_user_id, provider, provider_message_id,
                   delivery_status, template_key, metadata)
                values (%s, %s, 'email', 'outbound', %s, %s, %s, %s, 'resend', %s, %s, %s, %s::jsonb)
                returning id, channel, direction, subject, body_text, recipient_email,
                          sender_user_id, provider, provider_message_id, delivery_status,
                          template_key, created_at
                """,
                [organization_id, candidate_id, payload.subject.strip(), payload.body,
                 recipient, user_id, provider_id, delivery_status, payload.template_key,
                 '{"source":"candidate_profile"}'],
            )
            communication = cursor.fetchone()

    if delivery_status != "sent":
        raise HTTPException(status_code=502, detail=error_detail or "Email could not be sent. The failed attempt has been recorded.")
    return communication
