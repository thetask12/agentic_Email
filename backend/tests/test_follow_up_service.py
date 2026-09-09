import pytest

from app.services.follow_up_service import (
    schedule_follow_up, cancel_all_pending_for_lead, cancel_follow_up,
)
from app.repositories.repositories import follow_up_repo
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


@pytest.mark.asyncio
async def test_schedule_follow_up_requires_explicit_date():
    lead_id = new_id("lead")
    created = await schedule_follow_up(
        lead_id=lead_id, company_id=new_id("company"), original_email_id=new_id("email"),
        sequence_number=1, subject="Follow up", body="body", html_body="",
        scheduled_at="2026-09-01T10:00:00+00:00",
    )
    assert created["status"] == "SCHEDULED"
    assert created["scheduled_at"] == "2026-09-01T10:00:00+00:00"


@pytest.mark.asyncio
async def test_max_follow_ups_enforced():
    lead_id = new_id("lead")
    for i in range(1, 5):
        await schedule_follow_up(
            lead_id=lead_id, company_id=new_id("company"), original_email_id=new_id("email"),
            sequence_number=i, subject=f"F{i}", body="body", html_body="",
            scheduled_at="2026-09-01T10:00:00+00:00",
        )
    with pytest.raises(ValueError):
        await schedule_follow_up(
            lead_id=lead_id, company_id=new_id("company"), original_email_id=new_id("email"),
            sequence_number=5, subject="F5", body="body", html_body="",
            scheduled_at="2026-09-01T10:00:00+00:00",
        )


@pytest.mark.asyncio
async def test_reply_cancels_all_pending_follow_ups():
    lead_id = new_id("lead")
    for i in range(1, 3):
        await schedule_follow_up(
            lead_id=lead_id, company_id=new_id("company"), original_email_id=new_id("email"),
            sequence_number=i, subject=f"F{i}", body="body", html_body="",
            scheduled_at="2026-09-01T10:00:00+00:00",
        )
    cancelled_count = await cancel_all_pending_for_lead(lead_id, reason="REPLY_RECEIVED")
    assert cancelled_count == 2

    remaining = await follow_up_repo.find_where(lead_id=lead_id)
    assert all(r["status"] == "CANCELLED" for r in remaining)
    assert all(r["cancel_reason"] == "REPLY_RECEIVED" for r in remaining)


@pytest.mark.asyncio
async def test_cancel_follow_up_is_idempotent():
    lead_id = new_id("lead")
    created = await schedule_follow_up(
        lead_id=lead_id, company_id=new_id("company"), original_email_id=new_id("email"),
        sequence_number=1, subject="F1", body="body", html_body="",
        scheduled_at="2026-09-01T10:00:00+00:00",
    )
    first = await cancel_follow_up(created["follow_up_id"], reason="MANUAL")
    second = await cancel_follow_up(created["follow_up_id"], reason="MANUAL")
    assert first["status"] == "CANCELLED"
    assert second["status"] == "CANCELLED"
