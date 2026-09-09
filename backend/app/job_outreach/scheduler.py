"""
Job Outreach background scheduler — same asyncio-background-task pattern as
app/services/daily_search_scheduler.py (NOT APScheduler), but gated by the
persisted `automation_running` SETTINGS flag rather than a fixed business-
hours window: every tick, if the flag is false, the tick is a no-op. This is
the entire Start/Stop mechanism — starting the automation just flips the
flag true (see service.start()); the loop itself is always alive once the
FastAPI app is up (started from main.py's lifespan, mirroring the existing
scheduler), it just skips work while stopped.

Stop does NOT cancel already-PENDING EMAIL_QUEUE rows — a separate Apps
Script queue worker (apps-script-job-outreach/QueueWorker.gs) keeps sending
those independently of this flag; Stop only prevents new search cycles from
being started here.
"""
from __future__ import annotations

import asyncio
import logging

from app.job_outreach.settings_store import is_running

logger = logging.getLogger("job_outreach.scheduler")

# How often the loop wakes up to check the automation_running flag and
# possibly run one cycle. A full cycle already iterates every (role, city)
# combination and respects the daily cap internally (service.run_one_cycle),
# so this interval just controls how soon a fresh cycle starts after the
# previous one finishes (or after Start is pressed).
CYCLE_INTERVAL_SECONDS = 15 * 60  # 15 minutes, same cadence as the main system

_scheduler_task: asyncio.Task | None = None
_cycle_running = False


async def _run_cycle_guarded() -> None:
    global _cycle_running
    if _cycle_running:
        logger.warning("JOB_OUTREACH_SCHEDULER: previous cycle still running, skipping this tick")
        return
    _cycle_running = True
    try:
        from app.job_outreach.service import run_one_cycle
        result = await run_one_cycle()
        logger.info("JOB_OUTREACH_SCHEDULER: cycle finished result=%s", result)
    except Exception:
        logger.exception("JOB_OUTREACH_SCHEDULER: cycle failed")
    finally:
        _cycle_running = False


async def _scheduler_loop() -> None:
    while True:
        try:
            if await is_running():
                await _run_cycle_guarded()
            else:
                logger.debug("JOB_OUTREACH_SCHEDULER: automation_running is false, skipping tick")
        except Exception:
            logger.exception("JOB_OUTREACH_SCHEDULER: unexpected error in scheduler tick")
        await asyncio.sleep(CYCLE_INTERVAL_SECONDS)


async def trigger_cycle_now() -> None:
    """Runs one cycle immediately, guarded the same way as a normal scheduler
    tick (skips if a cycle is already in flight) — called by service.start()
    so pressing Start doesn't have to wait for the background loop's own
    CYCLE_INTERVAL_SECONDS sleep to elapse."""
    if await is_running():
        await _run_cycle_guarded()


def start_scheduler() -> None:
    """Ensures the background loop task exists. Safe to call repeatedly
    (e.g. every time service.start() is called) — a second call is a no-op
    if the loop is already alive; the loop itself decides whether to do
    work each tick based on the persisted flag, so it is always safe to
    have running in the background regardless of Start/Stop state."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("JOB_OUTREACH_SCHEDULER: background loop started (checks automation_running every %ds)",
                CYCLE_INTERVAL_SECONDS)


def stop_scheduler_task() -> None:
    """Cancels the background asyncio task entirely — used only on app
    shutdown (main.py lifespan), NOT by the Stop API endpoint (which just
    flips the automation_running flag so the loop keeps polling but does no
    work — see service.stop())."""
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        _scheduler_task = None
