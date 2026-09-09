from fastapi import APIRouter, HTTPException, Query

from app.repositories.repositories import follow_up_repo, lead_repo, company_repo, reply_repo, email_queue_repo
from app.schemas.requests import FollowUpCreateRequest, FollowUpPatchRequest
from app.services.follow_up_service import schedule_follow_up, cancel_follow_up
from app.services.email_queue_service import queue_email
from app.services.suppression_service import is_suppressed
from app.services.activity_service import log_activity
from app.utils.time_utils import date_range_bounds, parse_iso, is_due

router = APIRouter(prefix="/api", tags=["follow-ups"])


@router.get("/follow-ups")
async def list_follow_ups(filter: str | None = Query(None, description="today|tomorrow|this_week|next_7_days|overdue|custom"),
                           date_from: str | None = None, date_to: str | None = None,
                           status: str | None = None):
    items = await follow_up_repo.list_all()
    companies = {c["company_id"]: c for c in await company_repo.list_all()}

    if status:
        items = [f for f in items if f.get("status") == status]

    if filter and filter != "overdue":
        start, end = date_range_bounds(filter, date_from, date_to)
        if start and end:
            def in_range(f):
                try:
                    return start <= parse_iso(f.get("scheduled_at", "")) < end
                except ValueError:
                    return False
            items = [f for f in items if in_range(f)]
    elif filter == "overdue":
        items = [f for f in items if f.get("status") in ("SCHEDULED", "DUE") and is_due(f.get("scheduled_at", ""))]

    items.sort(key=lambda r: r.get("scheduled_at", ""))
    enriched = []
    for f in items:
        c = companies.get(f.get("company_id", ""), {})
        enriched.append({**f, "company_name": c.get("company_name", ""), "overdue": is_due(f.get("scheduled_at", "")) and f.get("status") in ("SCHEDULED", "DUE")})
    return {"items": enriched, "total": len(enriched)}


@router.post("/follow-ups")
async def create_follow_up(req: FollowUpCreateRequest):
    lead = await lead_repo.get_by_id(req.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    try:
        created = await schedule_follow_up(
            lead_id=req.lead_id, company_id=lead.get("company_id", ""),
            original_email_id=req.original_email_id, sequence_number=req.sequence_number,
            subject=req.subject, body=req.body, html_body=req.html_body,
            scheduled_at=req.scheduled_at, template_id=req.template_id, notes=req.notes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return created


@router.patch("/follow-ups/{follow_up_id}")
async def patch_follow_up(follow_up_id: str, req: FollowUpPatchRequest):
    fu = await follow_up_repo.get_by_id(follow_up_id)
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    if fu.get("status") in ("SENT", "CANCELLED"):
        raise HTTPException(400, "Cannot edit a sent or cancelled follow-up")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = await follow_up_repo.update(follow_up_id, patch)
    await log_activity(lead_id=fu["lead_id"], company_id=fu.get("company_id"),
                        activity_type="FOLLOW_UP_SCHEDULED", description="Follow-up rescheduled/edited",
                        created_by="user")
    return updated


@router.post("/follow-ups/{follow_up_id}/cancel")
async def cancel_follow_up_route(follow_up_id: str):
    updated = await cancel_follow_up(follow_up_id, reason="MANUAL")
    if not updated:
        raise HTTPException(404, "Follow-up not found")
    return updated


@router.post("/follow-ups/{follow_up_id}/skip")
async def skip_follow_up(follow_up_id: str):
    fu = await follow_up_repo.get_by_id(follow_up_id)
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    updated = await follow_up_repo.update(follow_up_id, {"status": "SKIPPED"})
    await log_activity(lead_id=fu["lead_id"], company_id=fu.get("company_id"),
                        activity_type="FOLLOW_UP_CANCELLED", description="Follow-up skipped by user",
                        created_by="user")
    return updated


@router.post("/follow-ups/{follow_up_id}/send-now")
async def send_follow_up_now(follow_up_id: str):
    """Pushes the follow-up into EMAIL_QUEUE immediately (scheduled_at=now).
    Actual sending still happens only via Apps Script's QueueWorker — the
    backend never sends email directly (rule 114)."""
    fu = await follow_up_repo.get_by_id(follow_up_id)
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    if fu.get("status") in ("SENT", "CANCELLED", "SKIPPED"):
        raise HTTPException(400, f"Follow-up is already {fu.get('status')}")

    replies = await reply_repo.find_where(lead_id=fu["lead_id"])
    if replies:
        await follow_up_repo.update(follow_up_id, {"status": "SKIPPED", "cancel_reason": "REPLIED"})
        raise HTTPException(409, "Lead has already replied — follow-up skipped instead of sent")

    recipient_lead = await lead_repo.get_by_id(fu["lead_id"])
    company = await company_repo.get_by_id(fu.get("company_id", "")) or {}
    from app.repositories.repositories import contact_repo
    contact = await contact_repo.get_by_id(recipient_lead.get("contact_id", "")) if recipient_lead else None
    recipient_email = contact.get("email") if contact else None
    if not recipient_email:
        raise HTTPException(400, "No recipient email on file for this lead")

    if await is_suppressed(recipient_email, fu.get("company_id")):
        await follow_up_repo.update(follow_up_id, {"status": "SKIPPED", "cancel_reason": "SUPPRESSED"})
        raise HTTPException(409, "Recipient is suppressed — follow-up skipped")

    from app.config.settings import get_settings
    settings = get_settings()
    pseudo_draft = {
        "email_id": fu["follow_up_id"], "lead_id": fu["lead_id"], "company_id": fu.get("company_id", ""),
        "recipient_email": recipient_email, "subject": fu["subject"],
        "plain_text_body": fu["body"], "html_body": fu.get("html_body", ""),
    }
    queued = await queue_email(pseudo_draft, kind="FOLLOW_UP", scheduled_at=None, priority="HIGH")
    await follow_up_repo.update(follow_up_id, {"status": "QUEUED"})
    return {"follow_up": await follow_up_repo.get_by_id(follow_up_id), "queue_item": queued}
