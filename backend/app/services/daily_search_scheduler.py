"""
Daily automated search scheduler (per explicit user instruction: search for
MIS Executive jobs in Chhattisgarh automatically every day, targeting up to
150 new outreach-ready leads, with no manual button click required).

No external scheduler dependency (APScheduler etc.) is added — this is a
single lightweight asyncio background task started from main.py's lifespan,
matching the project's existing pattern of small in-process services
(event_bus.py, search_cancellation.py) rather than pulling in new
infrastructure for a single daily job.

Behavior:
- Runs every ATTEMPT_INTERVAL_MINUTES (default 15) within business hours
  (BUSINESS_HOURS_START_IST..BUSINESS_HOURS_END_IST, default 09:00-21:00
  IST) — per explicit user instruction: rather than relying on a single
  daily attempt (which might come up short if sources are thin at that
  particular moment), the search is retried frequently across the day so a
  shortfall in one attempt can be made up by a later one on the SAME day.
  No attempts run overnight (21:00-09:00 IST) — companies/leads are scarce
  then anyway, and the 150/day cap is normally reached well before 21:00.
- Fixed search parameters: job_title="MIS Executive", state="Chhattisgarh".
- The 150/day cap is a TOTAL cap on newly-queued outreach emails for the
  day, shared with the one-time test-mode backlog resend utility
  (POST /api/settings/resend-test-mode-emails — see misc_routes.py): before
  each attempt, this counts how many EMAIL_QUEUE rows were already created
  today (from an earlier attempt today, a manual run, or the backlog
  resend) and only asks execute_search() for the REMAINING slots, so all
  attempts together never queue more than 150 emails in a calendar day.
- If an earlier attempt already reached 150 for the day, every later
  attempt that same day is skipped outright (no search is even started) —
  per explicit instruction: "ek baar mil gaya to fir chalne ki zarurat
  nahi". If today's total falls short of 150 even after all of today's
  attempts, the shortfall is NOT carried into tomorrow — each day starts
  a fresh 150 target (per explicit user confirmation).
- If a search run is still RUNNING when the next scheduled time arrives
  (shouldn't normally happen given the spacing, but guards against
  overlapping runs), the scheduler skips that tick rather than starting a
  second concurrent run.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.services.search_service import start_search, execute_search
from app.repositories.repositories import search_run_repo, email_queue_repo

logger = logging.getLogger("daily_search_scheduler")

IST = timezone(timedelta(hours=5, minutes=30))

# Attempts every 15 minutes within business hours, rather than a handful of
# fixed times, so a shortfall in an earlier attempt (e.g. sources thin in
# the morning) has many more chances to reach the daily 150 target before
# the day ends. Kept within business hours (not a full 24h spread) per
# explicit user preference — companies/leads are scarce overnight anyway.
BUSINESS_HOURS_START_IST = 9   # 09:00 IST
BUSINESS_HOURS_END_IST = 21    # 21:00 IST
ATTEMPT_INTERVAL_MINUTES = 15

DAILY_JOB_TITLE = "MIS Executive"
DAILY_STATE = "Chhattisgarh"
DAILY_TOTAL_EMAIL_CAP = 150
DAILY_SOURCES = ["naukri", "indeed", "linkedin", "apna", "foundit", "timesjobs", "workindia", "shine", "internshala", "google_search"]

_scheduler_task: asyncio.Task | None = None


def _business_hours_start(day: datetime) -> datetime:
    return day.replace(hour=BUSINESS_HOURS_START_IST, minute=0, second=0, microsecond=0)


def _business_hours_end(day: datetime) -> datetime:
    return day.replace(hour=BUSINESS_HOURS_END_IST, minute=0, second=0, microsecond=0)


def _next_run_at(now: datetime) -> datetime:
    today_start = _business_hours_start(now)
    today_end = _business_hours_end(now)

    if now < today_start:
        # Before business hours start today — first attempt is exactly at
        # the opening time, not clock-aligned to the interval.
        return today_start

    if now < today_end:
        # Within business hours — next attempt is the next
        # ATTEMPT_INTERVAL_MINUTES-aligned slot after `now`, counting from
        # today_start (so slots are always :00/:15/:30/:45 relative to the
        # 09:00 start, regardless of when the scheduler process itself
        # started).
        minutes_since_start = (now - today_start).total_seconds() / 60
        next_slot_index = int(minutes_since_start // ATTEMPT_INTERVAL_MINUTES) + 1
        next_at = today_start + timedelta(minutes=next_slot_index * ATTEMPT_INTERVAL_MINUTES)
        if next_at < today_end:
            return next_at
        # Rounded past the end of business hours — fall through to tomorrow.

    # At or after business hours end today — first attempt is tomorrow's
    # opening time.
    tomorrow = now + timedelta(days=1)
    return _business_hours_start(tomorrow)


async def _any_run_currently_active() -> bool:
    runs = await search_run_repo.list_all()
    return any(r.get("status") in ("PENDING", "RUNNING") for r in runs)


async def _emails_already_queued_today() -> int:
    """Counts EMAIL_QUEUE rows created today (IST) in any non-cancelled
    state — this covers both a real-mode search run's own queued emails and
    any backlog rows the resend-test-mode-emails utility reset to PENDING
    today, so both sources of sending share the same daily cap."""
    today_ist = datetime.now(IST).date()
    items = await email_queue_repo.list_all()
    count = 0
    for item in items:
        created_at = item.get("created_at") or ""
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(IST)
        except ValueError:
            continue
        if created_dt.date() == today_ist and item.get("status") != "SKIPPED":
            count += 1
    return count


async def emails_remaining_today() -> int:
    """Public helper so other callers (e.g. the resend-test-mode-emails
    admin endpoint in misc_routes.py) can share this scheduler's notion of
    the daily total-email cap instead of hardcoding their own number."""
    already_queued_today = await _emails_already_queued_today()
    return max(DAILY_TOTAL_EMAIL_CAP - already_queued_today, 0)


async def _run_daily_search() -> None:
    if await _any_run_currently_active():
        logger.warning("DAILY_SEARCH: skipped — another search run is already PENDING/RUNNING")
        return

    remaining_quota = await emails_remaining_today()
    if remaining_quota <= 0:
        logger.info("DAILY_SEARCH: skipped — today's %d-email cap already reached "
                    "(e.g. via the test-mode backlog resend)", DAILY_TOTAL_EMAIL_CAP)
        return

    logger.info("DAILY_SEARCH: starting automated run job_title=%r state=%r remaining_quota=%d of %d cap",
                DAILY_JOB_TITLE, DAILY_STATE, remaining_quota, DAILY_TOTAL_EMAIL_CAP)
    run = await start_search(
        job_title=DAILY_JOB_TITLE, state=DAILY_STATE, city=None,
        date_filter="", experience=None, sources=DAILY_SOURCES,
        result_limit=remaining_quota,
    )
    try:
        await execute_search(run["run_id"])
        logger.info("DAILY_SEARCH: run %s finished", run["run_id"])
    except Exception:
        logger.exception("DAILY_SEARCH: run %s failed", run["run_id"])
        await search_run_repo.update(run["run_id"], {"status": "FAILED"})


async def _scheduler_loop() -> None:
    while True:
        now = datetime.now(IST)
        next_at = _next_run_at(now)
        sleep_seconds = (next_at - now).total_seconds()
        logger.info("DAILY_SEARCH: next automated run scheduled at %s IST (in %.0f minutes)",
                    next_at.isoformat(), sleep_seconds / 60)
        await asyncio.sleep(sleep_seconds)
        try:
            await _run_daily_search()
        except Exception:
            logger.exception("DAILY_SEARCH: unexpected error in scheduler tick")


def start_daily_search_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("DAILY_SEARCH: scheduler started (every %d min, %02d:00-%02d:00 IST, "
                "%r in %r, daily cap=%d emails)",
                ATTEMPT_INTERVAL_MINUTES, BUSINESS_HOURS_START_IST, BUSINESS_HOURS_END_IST,
                DAILY_JOB_TITLE, DAILY_STATE, DAILY_TOTAL_EMAIL_CAP)


def stop_daily_search_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        _scheduler_task = None
