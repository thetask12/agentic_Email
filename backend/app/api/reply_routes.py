from fastapi import APIRouter, Header, HTTPException

from app.repositories.repositories import reply_repo, conversation_repo, email_draft_repo, email_queue_repo, follow_up_repo, lead_repo, company_repo
from app.schemas.requests import ReplyWebhookRequest
from app.services.reply_service import ingest_reply
from app.config.settings import get_settings

router = APIRouter(prefix="/api", tags=["replies"])


@router.get("/replies")
async def list_replies(reply_type: str | None = None, limit: int = 300):
    items = await reply_repo.list_all()
    if reply_type:
        items = [r for r in items if r.get("reply_type") == reply_type]
    items.sort(key=lambda r: r.get("received_at", ""), reverse=True)
    companies = {c["company_id"]: c for c in await company_repo.list_all()}
    leads = {l["lead_id"]: l for l in await lead_repo.list_all()}
    enriched = []
    for r in items[:limit]:
        c = companies.get(r.get("company_id", ""), {})
        l = leads.get(r.get("lead_id", ""), {})
        enriched.append({**r, "company_name": c.get("company_name", ""), "owner": l.get("owner", ""),
                          "lead_status": l.get("status", "")})
    return {"items": enriched, "total": len(items)}


@router.get("/replies/{reply_id}")
async def get_reply(reply_id: str):
    reply = await reply_repo.get_by_id(reply_id)
    if not reply:
        raise HTTPException(404, "Reply not found")
    return reply


@router.get("/conversations/{lead_id}")
async def get_conversation(lead_id: str):
    """Chronological timeline of outbound emails (from EMAIL_QUEUE, status=SENT),
    sent follow-ups, and inbound replies for a lead — built from real records only."""
    lead = await lead_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    queue_items = await email_queue_repo.find_where(lead_id=lead_id)
    replies = await reply_repo.find_where(lead_id=lead_id)
    follow_ups = await follow_up_repo.find_where(lead_id=lead_id)

    messages = []
    for q in queue_items:
        if q.get("status") == "SENT":
            messages.append({
                "direction": "OUTBOUND", "timestamp": q.get("sent_at", ""), "subject": q.get("subject", ""),
                "body": q.get("body", ""), "kind": q.get("kind", "INITIAL"), "message_id": q.get("message_id", ""),
            })
    for r in replies:
        messages.append({
            "direction": "INBOUND", "timestamp": r.get("received_at", ""), "subject": r.get("subject", ""),
            "body": r.get("body_text", ""), "from_email": r.get("from_email", ""),
            "reply_type": r.get("reply_type", ""), "sentiment": r.get("sentiment", ""),
            "ai_summary": r.get("ai_summary", ""), "suggested_response": r.get("suggested_response", ""),
        })
    messages.sort(key=lambda m: m.get("timestamp", ""))
    convo = await conversation_repo.find_where(lead_id=lead_id)
    return {"lead_id": lead_id, "messages": messages, "follow_ups": follow_ups, "conversation": convo[0] if convo else None}


@router.post("/replies/webhook")
async def replies_webhook(req: ReplyWebhookRequest, x_apps_script_secret: str | None = Header(default=None)):
    """Called by Apps Script's ReplyScanner after it detects a genuinely new
    inbound Gmail message on a tracked thread. Never called from the frontend."""
    settings = get_settings()
    if settings.apps_script_shared_secret and x_apps_script_secret != settings.apps_script_shared_secret:
        raise HTTPException(401, "Invalid shared secret")
    created = await ingest_reply(req.model_dump())
    return created
