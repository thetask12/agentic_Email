"""
Follow-up scheduling/cancellation (System.txt sections 31-41, 124-127).

The USER controls follow-up dates by default. AUTO_FOLLOWUP_AUTOMATION must
be explicitly enabled (via SETTINGS) before any date is auto-suggested —
and even then, AI only recommends, it never silently schedules or sends.
"""
from app.config.settings import get_settings
from app.models.enums import FollowUpStatus, EmailEventType, LeadStatus
from app.repositories.repositories import (
    follow_up_repo, lead_repo, email_event_repo, reply_repo,
)
from app.services.activity_service import log_activity
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


async def _write_event(*, lead_id: str, company_id: str, event_type: str, metadata: dict | None = None) -> None:
    import json
    await email_event_repo.create({
        "event_id": new_id("event"),
        "email_id": "",
        "lead_id": lead_id,
        "company_id": company_id,
        "event_type": event_type,
        "timestamp": iso_now(),
        "message_id": "",
        "provider": "system",
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        "created_at": iso_now(),
    })


async def schedule_follow_up(*, lead_id: str, company_id: str, original_email_id: str,
                              sequence_number: int, subject: str, body: str, html_body: str,
                              scheduled_at: str, template_id: str = "", notes: str = "") -> dict:
    """User-initiated scheduling only. scheduled_at MUST be supplied by the caller
    (the API layer requires it in the request body) — this function never invents a date."""
    settings = get_settings()
    existing = await follow_up_repo.find_where(lead_id=lead_id)
    active_count = sum(1 for f in existing if f.get("status") in (
        FollowUpStatus.SCHEDULED.value, FollowUpStatus.DUE.value, FollowUpStatus.QUEUED.value,
        FollowUpStatus.SENT.value))
    if active_count >= settings.max_follow_ups:
        raise ValueError(f"MAX_FOLLOW_UPS ({settings.max_follow_ups}) reached for this lead")

    record = {
        "follow_up_id": new_id("followup"),
        "lead_id": lead_id,
        "company_id": company_id,
        "original_email_id": original_email_id,
        "sequence_number": sequence_number,
        "template_id": template_id,
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "scheduled_at": scheduled_at,
        "status": FollowUpStatus.SCHEDULED.value,
        "sent_at": "",
        "message_id": "",
        "reply_received": False,
        "cancelled_at": "",
        "cancel_reason": "",
        "notes": notes,
    }
    created = await follow_up_repo.create(record)
    await _write_event(lead_id=lead_id, company_id=company_id,
                        event_type=EmailEventType.FOLLOW_UP_SCHEDULED.value,
                        metadata={"follow_up_id": created["follow_up_id"], "scheduled_at": scheduled_at})
    await log_activity(lead_id=lead_id, company_id=company_id, activity_type="FOLLOW_UP_SCHEDULED",
                        description=f"Follow-up #{sequence_number} scheduled for {scheduled_at}")
    return created


async def cancel_follow_up(follow_up_id: str, *, reason: str = "MANUAL") -> dict | None:
    fu = await follow_up_repo.get_by_id(follow_up_id)
    if not fu:
        return None
    if fu.get("status") in (FollowUpStatus.SENT.value, FollowUpStatus.CANCELLED.value):
        return fu
    updated = await follow_up_repo.update(follow_up_id, {
        "status": FollowUpStatus.CANCELLED.value,
        "cancelled_at": iso_now(),
        "cancel_reason": reason,
    })
    await _write_event(lead_id=fu["lead_id"], company_id=fu.get("company_id", ""),
                        event_type=EmailEventType.CANCELLED.value,
                        metadata={"follow_up_id": follow_up_id, "reason": reason})
    await log_activity(lead_id=fu["lead_id"], company_id=fu.get("company_id", ""),
                        activity_type="FOLLOW_UP_CANCELLED",
                        description=f"Follow-up cancelled ({reason})")
    return updated


async def cancel_all_pending_for_lead(lead_id: str, *, reason: str = "REPLY_RECEIVED") -> int:
    """Called when a reply arrives (System.txt sections 15, 36, 41, 124): auto-cancel
    every pending follow-up for the lead. Returns count cancelled."""
    pending = await follow_up_repo.find_where(lead_id=lead_id)
    count = 0
    for fu in pending:
        if fu.get("status") in (FollowUpStatus.SCHEDULED.value, FollowUpStatus.DUE.value,
                                 FollowUpStatus.QUEUED.value):
            await cancel_follow_up(fu["follow_up_id"], reason=reason)
            count += 1
    return count


async def mark_due_follow_ups() -> int:
    """Recompute SCHEDULED -> DUE transitions for follow-ups whose scheduled_at has
    passed but haven't been sent yet. Pure status-derivation, no sending — Apps
    Script's FollowUpWorker is what actually sends."""
    from app.utils.time_utils import is_due
    rows = await follow_up_repo.find_where(status=FollowUpStatus.SCHEDULED.value)
    count = 0
    for r in rows:
        if is_due(r.get("scheduled_at", "")):
            await follow_up_repo.update(r["follow_up_id"], {"status": FollowUpStatus.DUE.value})
            count += 1
    return count
