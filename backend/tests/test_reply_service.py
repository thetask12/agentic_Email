import pytest

from app.services.reply_service import ingest_reply
from app.services.follow_up_service import schedule_follow_up
from app.repositories.repositories import reply_repo, lead_repo
from app.utils.ids import new_id


@pytest.mark.asyncio
async def test_ingest_reply_is_idempotent_by_message_id():
    lead_id = new_id("lead")
    await lead_repo.create({"lead_id": lead_id, "status": "CONTACTED"})
    message_id = new_id("msg")

    payload = {
        "lead_id": lead_id, "company_id": "", "email_id": "", "thread_id": new_id("thread"),
        "message_id": message_id, "from_email": "hr@example.com", "subject": "Re: hello",
        "body_text": "Thanks, tell me more.",
    }
    first = await ingest_reply(payload)
    second = await ingest_reply(payload)
    assert first["reply_id"] == second["reply_id"]

    all_replies = await reply_repo.find_where(message_id=message_id)
    assert len(all_replies) == 1


@pytest.mark.asyncio
async def test_reply_cancels_pending_follow_ups_and_updates_lead_status():
    lead_id = new_id("lead")
    await lead_repo.create({"lead_id": lead_id, "status": "CONTACTED"})
    await schedule_follow_up(
        lead_id=lead_id, company_id="", original_email_id=new_id("email"), sequence_number=1,
        subject="F1", body="body", html_body="", scheduled_at="2026-09-01T10:00:00+00:00",
    )

    await ingest_reply({
        "lead_id": lead_id, "company_id": "", "email_id": "", "thread_id": new_id("thread"),
        "message_id": new_id("msg"), "from_email": "hr@example.com", "subject": "Re: hello",
        "body_text": "unsubscribe me please",
    })

    lead = await lead_repo.get_by_id(lead_id)
    assert lead["status"] == "SUPPRESSED"
