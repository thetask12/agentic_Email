"""
Typed helpers over the SETTINGS tab (key/value rows) — the single source of
truth for the Start/Stop automation flag and the daily email cap/counter,
shared between the frontend Start/Stop buttons, the scheduler loop, and any
route that needs to read them. See docs/job-outreach-schema.md SETTINGS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.job_outreach.repositories import settings_repo
from app.job_outreach.config import get_job_outreach_settings
from app.utils.time_utils import iso_now

IST = timezone(timedelta(hours=5, minutes=30))

KEY_AUTOMATION_RUNNING = "automation_running"
KEY_DAILY_EMAIL_CAP = "daily_email_cap"
KEY_EMAILS_SENT_TODAY = "emails_sent_today"
KEY_EMAILS_SENT_DATE = "emails_sent_date"


def _today_ist_date() -> str:
    return datetime.now(IST).date().isoformat()


async def _get_raw(key: str) -> str | None:
    row = await settings_repo.get_by_id(key)
    return row.get("value") if row else None


async def _set_raw(key: str, value: str, description: str = "") -> None:
    existing = await settings_repo.get_by_id(key)
    if existing:
        await settings_repo.update(key, {"value": value, "updated_at": iso_now()})
    else:
        await settings_repo.create({
            "key": key, "value": value, "description": description, "updated_at": iso_now(),
        })


async def ensure_seeded() -> None:
    """Seeds the four SETTINGS rows if missing — idempotent, safe to call on
    every startup (mirrors bootstrap_service.seed_defaults() for the main
    system, but scoped to this module's own sheet)."""
    defaults = {
        KEY_AUTOMATION_RUNNING: ("false", "Whether the Start/Stop automation loop is currently active."),
        KEY_DAILY_EMAIL_CAP: (str(get_job_outreach_settings().job_outreach_daily_email_cap),
                               "Max new application emails queued per calendar day."),
        KEY_EMAILS_SENT_TODAY: ("0", "Running counter of emails queued today, reset at midnight IST."),
        KEY_EMAILS_SENT_DATE: (_today_ist_date(), "IST date (YYYY-MM-DD) the counter above applies to."),
    }
    for key, (value, description) in defaults.items():
        if await settings_repo.get_by_id(key) is None:
            await settings_repo.create({
                "key": key, "value": value, "description": description, "updated_at": iso_now(),
            })


async def is_running() -> bool:
    raw = await _get_raw(KEY_AUTOMATION_RUNNING)
    return str(raw).strip().lower() == "true"


async def set_running(value: bool) -> None:
    await _set_raw(KEY_AUTOMATION_RUNNING, "true" if value else "false",
                    "Whether the Start/Stop automation loop is currently active.")


async def get_daily_cap() -> int:
    raw = await _get_raw(KEY_DAILY_EMAIL_CAP)
    try:
        return int(raw) if raw else get_job_outreach_settings().job_outreach_daily_email_cap
    except ValueError:
        return get_job_outreach_settings().job_outreach_daily_email_cap


async def _roll_counter_if_new_day() -> int:
    """Resets emails_sent_today to 0 if emails_sent_date is not today (IST),
    same "never carry a shortfall/overage into tomorrow" rule as the main
    system's daily_search_scheduler. Returns the (possibly just-reset)
    current count."""
    today = _today_ist_date()
    stored_date = await _get_raw(KEY_EMAILS_SENT_DATE)
    if stored_date != today:
        await _set_raw(KEY_EMAILS_SENT_DATE, today, "IST date (YYYY-MM-DD) the counter above applies to.")
        await _set_raw(KEY_EMAILS_SENT_TODAY, "0", "Running counter of emails queued today, reset at midnight IST.")
        return 0
    raw = await _get_raw(KEY_EMAILS_SENT_TODAY)
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


async def emails_sent_today() -> int:
    return await _roll_counter_if_new_day()


async def emails_remaining_today() -> int:
    sent = await emails_sent_today()
    cap = await get_daily_cap()
    return max(cap - sent, 0)


async def increment_emails_sent_today(by: int = 1) -> int:
    current = await _roll_counter_if_new_day()
    new_value = current + by
    await _set_raw(KEY_EMAILS_SENT_TODAY, str(new_value),
                    "Running counter of emails queued today, reset at midnight IST.")
    return new_value
