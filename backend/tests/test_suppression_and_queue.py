import pytest

from app.services.suppression_service import is_suppressed, suppress
from app.services.email_queue_service import queue_email
from app.repositories.repositories import email_draft_repo, email_queue_repo
from app.utils.ids import new_id


@pytest.mark.asyncio
async def test_suppression_blocks_recipient():
    email = f"blocked_{new_id('test')}@example.com"
    assert await is_suppressed(email) is False
    await suppress(email, reason="MANUAL", source="test")
    assert await is_suppressed(email) is True


@pytest.mark.asyncio
async def test_queue_email_marks_suppressed_recipient_skipped():
    email = f"suppressed_{new_id('test')}@example.com"
    await suppress(email, reason="MANUAL", source="test")

    draft = await email_draft_repo.create({
        "email_id": new_id("email"), "lead_id": new_id("lead"), "company_id": new_id("company"),
        "template_id": "", "recipient_email": email, "sender_email": "sender@botivate.in",
        "subject": "Test", "plain_text_body": "Body", "html_body": "", "status": "APPROVED",
    })
    queued = await queue_email(draft)
    assert queued["status"] == "SKIPPED"
    assert queued["error_message"] == "SUPPRESSED"


@pytest.mark.asyncio
async def test_queue_email_is_idempotent_per_draft():
    email = f"idempotent_{new_id('test')}@example.com"
    draft = await email_draft_repo.create({
        "email_id": new_id("email"), "lead_id": new_id("lead"), "company_id": new_id("company"),
        "template_id": "", "recipient_email": email, "sender_email": "sender@botivate.in",
        "subject": "Test", "plain_text_body": "Body", "html_body": "", "status": "APPROVED",
    })
    first = await queue_email(draft)
    second = await queue_email(draft)
    assert first["queue_id"] == second["queue_id"]

    all_for_email = await email_queue_repo.find_where(email_id=draft["email_id"])
    assert len(all_for_email) == 1
