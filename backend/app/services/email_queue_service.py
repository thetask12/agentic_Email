"""
Email queue creation (System.txt sections 18, 114). The FastAPI backend
NEVER sends email directly — it only creates/updates EMAIL_QUEUE rows.
Google Apps Script's QueueWorker is the only thing that actually calls
GmailApp.sendEmail. This service also writes the CREATED/QUEUED EMAIL_EVENTS
and keeps EMAIL_DRAFTS/LEADS status in sync.
"""
from app.config.settings import get_settings
from app.models.enums import QueueStatus, EmailDraftStatus, LeadStatus, EmailEventType, QueueKind
from app.repositories.repositories import email_queue_repo, email_draft_repo, lead_repo, email_event_repo
from app.services.activity_service import log_activity
from app.services.suppression_service import is_suppressed
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


async def _write_event(*, email_id: str, lead_id: str, company_id: str, event_type: str,
                        message_id: str = "", metadata: dict | None = None) -> None:
    import json
    await email_event_repo.create({
        "event_id": new_id("event"),
        "email_id": email_id,
        "lead_id": lead_id,
        "company_id": company_id,
        "event_type": event_type,
        "timestamp": iso_now(),
        "message_id": message_id,
        "provider": "gmail",
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        "created_at": iso_now(),
    })


async def queue_email(email_draft: dict, *, kind: str = QueueKind.INITIAL.value,
                       scheduled_at: str | None = None, priority: str = "NORMAL") -> dict:
    """Move an approved EMAIL_DRAFTS row into EMAIL_QUEUE. Idempotent per email_id —
    if a PENDING/PROCESSING/SENT queue item already exists for this email_id, return it
    instead of creating a duplicate (rule 135: idempotency)."""
    settings = get_settings()
    lead_id = email_draft["lead_id"]
    company_id = email_draft.get("company_id", "")
    recipient = email_draft["recipient_email"]

    existing_items = await email_queue_repo.find_where(email_id=email_draft["email_id"])
    for item in existing_items:
        if item.get("status") in (QueueStatus.PENDING.value, QueueStatus.PROCESSING.value, QueueStatus.SENT.value):
            return item

    suppressed = await is_suppressed(recipient, company_id)
    status = QueueStatus.SKIPPED.value if suppressed else QueueStatus.PENDING.value

    record = {
        "queue_id": new_id("queue"),
        "email_id": email_draft["email_id"],
        "lead_id": lead_id,
        "recipient_email": recipient,
        "sender_email": settings.botivate_sender_email,
        "subject": email_draft["subject"],
        "body": email_draft.get("plain_text_body", ""),
        "html_body": email_draft.get("html_body", ""),
        "kind": kind,
        "priority": priority,
        "scheduled_at": scheduled_at or iso_now(),
        "status": status,
        "attempts": 0,
        "max_attempts": settings.queue_max_attempts,
        "last_attempt_at": "",
        "sent_at": "",
        "message_id": "",
        "thread_id": "",
        "error_message": "SUPPRESSED" if suppressed else "",
        "test_mode": settings.email_test_mode,
    }
    created = await email_queue_repo.create(record)

    await email_draft_repo.update(email_draft["email_id"], {"status": EmailDraftStatus.QUEUED.value})
    await lead_repo.update(lead_id, {"status": LeadStatus.QUEUED.value})
    await _write_event(email_id=email_draft["email_id"], lead_id=lead_id, company_id=company_id,
                        event_type=EmailEventType.QUEUED.value)
    await log_activity(lead_id=lead_id, company_id=company_id, activity_type="EMAIL_QUEUED",
                        description=f"Email queued for {recipient}" + (" (SUPPRESSED)" if suppressed else ""))
    return created
