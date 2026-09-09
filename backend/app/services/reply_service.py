"""
Reply ingestion service (System.txt sections 24-30, 57-61, 84, 128-129).

This is called from the /api/replies/webhook endpoint, which Apps Script's
ReplyScanner POSTs to after it detects a genuinely new inbound Gmail
message (see apps-script/ReplyScanner.gs). The backend never invents a
reply on its own — it only reacts to what Apps Script observed in Gmail.
"""
import json

from app.models.enums import LeadStatus, EmailEventType, ConversationStatus, MessageDirection
from app.repositories.repositories import (
    reply_repo, lead_repo, conversation_repo, email_event_repo, email_draft_repo,
)
from app.agents.reply_analysis import analyze_reply
from app.services.activity_service import log_activity
from app.services.follow_up_service import cancel_all_pending_for_lead
from app.services.suppression_service import suppress
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


async def ingest_reply(payload: dict) -> dict:
    """payload fields expected from Apps Script webhook:
    lead_id, company_id, email_id, thread_id, message_id, in_reply_to,
    from_email, from_name, to_email, subject, body_text, body_html, received_at
    """
    message_id = payload.get("message_id", "")
    # Idempotency: never create two REPLIES rows for the same message_id.
    existing = await reply_repo.find_one_where(message_id=message_id) if message_id else None
    if existing:
        return existing

    lead_id = payload.get("lead_id", "")
    company_id = payload.get("company_id", "")
    original_email_id = payload.get("email_id", "")

    original_subject = payload.get("subject", "")
    original_excerpt = ""
    if original_email_id:
        draft = await email_draft_repo.get_by_id(original_email_id)
        if draft:
            original_excerpt = draft.get("plain_text_body", "")

    analysis = analyze_reply(
        original_subject=original_subject,
        original_body_excerpt=original_excerpt,
        reply_body=payload.get("body_text", ""),
    )

    reply_record = {
        "reply_id": new_id("reply"),
        "lead_id": lead_id,
        "company_id": company_id,
        "email_id": original_email_id,
        "thread_id": payload.get("thread_id", ""),
        "message_id": message_id,
        "in_reply_to": payload.get("in_reply_to", ""),
        "from_email": payload.get("from_email", ""),
        "from_name": payload.get("from_name", ""),
        "to_email": payload.get("to_email", ""),
        "subject": payload.get("subject", ""),
        "body_text": payload.get("body_text", ""),
        "body_html": payload.get("body_html", ""),
        "received_at": payload.get("received_at") or iso_now(),
        "reply_type": analysis["reply_type"],
        "sentiment": analysis["sentiment"],
        "intent": analysis["reply_type"],
        "ai_summary": analysis["summary"],
        "requires_action": analysis["recommended_next_action"] not in ("NO_ACTION",),
        "action_type": analysis["recommended_next_action"],
        "priority": analysis["priority"],
        "suggested_response": analysis["suggested_response"],
    }
    created = await reply_repo.create(reply_record)

    if lead_id:
        await email_event_repo.create({
            "event_id": new_id("event"),
            "email_id": original_email_id,
            "lead_id": lead_id,
            "company_id": company_id,
            "event_type": EmailEventType.REPLIED.value,
            "timestamp": iso_now(),
            "message_id": message_id,
            "provider": "gmail",
            "metadata": json.dumps({"reply_id": created["reply_id"]}),
            "created_at": iso_now(),
        })

        new_status = analysis["lead_status"]
        await lead_repo.update(lead_id, {
            "status": new_status,
            "next_action": analysis["recommended_next_action"],
        })

        cancelled_count = await cancel_all_pending_for_lead(lead_id, reason="REPLY_RECEIVED")

        if analysis["reply_type"] == "UNSUBSCRIBE":
            await suppress(payload.get("from_email", ""), company_id=company_id,
                            reason="UNSUBSCRIBE", source="reply")
            await lead_repo.update(lead_id, {"status": LeadStatus.SUPPRESSED.value})

        thread_id = payload.get("thread_id", "")
        convo = await conversation_repo.find_one_where(thread_id=thread_id) if thread_id else None
        if convo:
            await conversation_repo.update(convo["conversation_id"], {
                "status": ConversationStatus.ACTIVE.value,
                "last_message_at": reply_record["received_at"],
                "last_message_direction": MessageDirection.INBOUND.value,
                "message_count": int(convo.get("message_count") or 0) + 1,
            })
        else:
            await conversation_repo.create({
                "conversation_id": new_id("conversation"),
                "lead_id": lead_id,
                "company_id": company_id,
                "thread_id": thread_id,
                "status": ConversationStatus.ACTIVE.value,
                "last_message_at": reply_record["received_at"],
                "last_message_direction": MessageDirection.INBOUND.value,
                "message_count": 1,
            })

        await log_activity(
            lead_id=lead_id, company_id=company_id, activity_type="REPLY_RECEIVED",
            description=f"Reply received from {payload.get('from_email', '')} — classified {analysis['reply_type']}",
            metadata={"reply_id": created["reply_id"], "follow_ups_cancelled": cancelled_count},
        )

    return created
