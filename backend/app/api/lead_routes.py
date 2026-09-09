from fastapi import APIRouter, HTTPException, Query

from app.repositories.repositories import (
    lead_repo, company_repo, job_repo, contact_repo, email_draft_repo, email_queue_repo,
    follow_up_repo, reply_repo, activity_log_repo, lead_note_repo, conversation_repo,
)
from app.schemas.requests import LeadPatchRequest, NoteRequest
from app.agents.email_generation import generate_initial_email
from app.services.activity_service import log_activity
from app.utils.ids import new_id
from app.config.settings import get_settings

router = APIRouter(prefix="/api", tags=["leads"])


async def _enrich_lead(lead: dict) -> dict:
    company = await company_repo.get_by_id(lead.get("company_id", "")) or {}
    job = await job_repo.get_by_id(lead.get("job_id", "")) or {}
    contact = await contact_repo.get_by_id(lead.get("contact_id", "")) or {}
    drafts = await email_draft_repo.find_where(lead_id=lead["lead_id"])
    queue_items = await email_queue_repo.find_where(lead_id=lead["lead_id"])
    replies = await reply_repo.find_where(lead_id=lead["lead_id"])
    follow_ups = await follow_up_repo.find_where(lead_id=lead["lead_id"])
    return {
        **lead, "company": company, "job": job, "contact": contact,
        "email_drafts": drafts, "email_queue": queue_items, "replies": replies,
        "follow_ups": follow_ups,
        "email_sent": any(q.get("status") == "SENT" for q in queue_items),
        "has_reply": len(replies) > 0,
    }


@router.get("/leads")
async def list_leads(
    state: str | None = None, city: str | None = None, source: str | None = None,
    job_title: str | None = None, company: str | None = None, status: str | None = None,
    priority: str | None = None, email_status: str | None = None, reply_status: str | None = None,
    follow_up_status: str | None = None, search: str | None = None,
    limit: int = Query(300, le=2000),
):
    leads = await lead_repo.list_all()
    companies = {c["company_id"]: c for c in await company_repo.list_all()}
    jobs = {j["job_id"]: j for j in await job_repo.list_all()}
    queue_by_lead: dict[str, list] = {}
    for q in await email_queue_repo.list_all():
        queue_by_lead.setdefault(q.get("lead_id", ""), []).append(q)
    replies_by_lead: dict[str, list] = {}
    for r in await reply_repo.list_all():
        replies_by_lead.setdefault(r.get("lead_id", ""), []).append(r)
    fu_by_lead: dict[str, list] = {}
    for f in await follow_up_repo.list_all():
        fu_by_lead.setdefault(f.get("lead_id", ""), []).append(f)

    def matches(l: dict) -> bool:
        c = companies.get(l.get("company_id", ""), {})
        j = jobs.get(l.get("job_id", ""), {})
        if state and c.get("state", "").lower() != state.lower():
            return False
        if city and c.get("city", "").lower() != city.lower():
            return False
        if source and j.get("source") != source:
            return False
        if job_title and job_title.lower() not in j.get("job_title", "").lower():
            return False
        if company and company.lower() not in c.get("company_name", "").lower():
            return False
        if status and l.get("status") != status:
            return False
        if priority and l.get("priority") != priority:
            return False
        queue_items = queue_by_lead.get(l["lead_id"], [])
        if email_status == "NOT_SENT" and any(q.get("status") == "SENT" for q in queue_items):
            return False
        if email_status == "SENT" and not any(q.get("status") == "SENT" for q in queue_items):
            return False
        if reply_status == "REPLIED" and not replies_by_lead.get(l["lead_id"]):
            return False
        if reply_status == "NOT_REPLIED" and replies_by_lead.get(l["lead_id"]):
            return False
        fus = fu_by_lead.get(l["lead_id"], [])
        if follow_up_status == "NO_FOLLOW_UP" and fus:
            return False
        if follow_up_status == "FOLLOW_UP_SCHEDULED" and not any(f.get("status") == "SCHEDULED" for f in fus):
            return False
        if follow_up_status == "FOLLOW_UP_DUE" and not any(f.get("status") == "DUE" for f in fus):
            return False
        if follow_up_status == "FOLLOW_UP_SENT" and not any(f.get("status") == "SENT" for f in fus):
            return False
        if follow_up_status == "FOLLOW_UP_CANCELLED" and not any(f.get("status") == "CANCELLED" for f in fus):
            return False
        if search:
            s = search.lower()
            hay = f"{c.get('company_name','')} {j.get('job_title','')} {c.get('city','')}".lower()
            if s not in hay:
                return False
        return True

    filtered = [l for l in leads if matches(l)]
    filtered.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    result = []
    for l in filtered[:limit]:
        c = companies.get(l.get("company_id", ""), {})
        j = jobs.get(l.get("job_id", ""), {})
        queue_items = queue_by_lead.get(l["lead_id"], [])
        sent_item = next((q for q in queue_items if q.get("status") == "SENT"), None)
        result.append({
            **l, "company_name": c.get("company_name", ""), "job_title": j.get("job_title", ""),
            "source": j.get("source", ""), "email_sent": sent_item is not None,
            "sent_at": sent_item.get("sent_at", "") if sent_item else "",
            "has_reply": bool(replies_by_lead.get(l["lead_id"])),
            "follow_up_count": len(fu_by_lead.get(l["lead_id"], [])),
        })
    return {"items": result, "total": len(filtered)}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    lead = await lead_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    enriched = await _enrich_lead(lead)
    enriched["activity"] = await activity_log_repo.find_where(lead_id=lead_id)
    enriched["notes"] = await lead_note_repo.find_where(lead_id=lead_id)
    conv = await conversation_repo.find_where(lead_id=lead_id)
    enriched["conversations"] = conv
    return enriched


@router.patch("/leads/{lead_id}")
async def patch_lead(lead_id: str, req: LeadPatchRequest):
    lead = await lead_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    if not patch:
        return lead
    updated = await lead_repo.update(lead_id, patch)
    await log_activity(lead_id=lead_id, company_id=lead.get("company_id"), activity_type="STATUS_CHANGED",
                        description=f"Manual update: {patch}", created_by="user")
    return updated


@router.post("/leads/{lead_id}/notes")
async def add_note(lead_id: str, req: NoteRequest):
    lead = await lead_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    note = await lead_note_repo.create({
        "note_id": new_id("note"), "lead_id": lead_id, "note": req.note, "created_by": req.created_by,
    })
    await log_activity(lead_id=lead_id, company_id=lead.get("company_id"), activity_type="NOTE_ADDED",
                        description=req.note[:200], created_by=req.created_by)
    return note


@router.post("/leads/{lead_id}/generate-email")
async def generate_email_for_lead(lead_id: str):
    lead = await lead_repo.get_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    settings = get_settings()
    company = await company_repo.get_by_id(lead.get("company_id", "")) or {}
    job = await job_repo.get_by_id(lead.get("job_id", "")) or {}
    contact = await contact_repo.get_by_id(lead.get("contact_id", "")) or {}
    if not contact.get("email"):
        raise HTTPException(400, "No verified email found for this lead's company")

    signals = [s for s in (lead.get("automation_signals") or "").split(",") if s]
    pains = [p for p in (lead.get("pain_points") or "").split(",") if p]

    generated = generate_initial_email(
        company_name=company.get("company_name", ""), job_title=job.get("job_title", ""),
        city=company.get("city"), contact_name=contact.get("contact_name") or None,
        automation_signals=signals, pain_points=pains,
        sender_name=settings.botivate_sender_name, botivate_website=settings.botivate_website_url,
        autorocket_website=settings.autorocket_website_url,
    )
    email_id = new_id("email")
    draft = await email_draft_repo.create({
        "email_id": email_id, "lead_id": lead_id, "company_id": lead.get("company_id", ""),
        "template_id": "", "recipient_email": contact["email"],
        "sender_email": settings.botivate_sender_email, "subject": generated["subject"],
        "plain_text_body": generated["plain_text_body"], "html_body": generated["html_body"],
        "personalization_points": ",".join(generated["personalization_points"]),
        "facts_used": ",".join(generated["facts_used"]), "confidence": generated["confidence"],
        "status": "DRAFT",
    })
    await lead_repo.update(lead_id, {"status": "EMAIL_DRAFTED"})
    await log_activity(lead_id=lead_id, company_id=lead.get("company_id"), activity_type="EMAIL_GENERATED",
                        description="Email (re)generated on request", created_by="user")
    return draft
