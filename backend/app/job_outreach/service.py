"""
Orchestration for the Job Outreach module: find company -> find official
email -> generate one application email -> queue it. No lead scoring, no
CRM pipeline, no follow-ups — exactly one email per company, ever (enforced
via SUPPRESSION_LIST + a COMPANIES lookup before ever emailing again).
"""
from __future__ import annotations

import logging

from app.job_outreach.config import get_job_outreach_settings
from app.job_outreach.models import ACCEPTED_EMAIL_TYPES, ROLES, ALL_LOCATIONS, INDIA_LOCATIONS
from app.job_outreach.repositories import (
    job_listing_repo, company_repo, email_queue_repo, suppression_repo,
    search_run_repo, activity_log_repo,
)
from app.job_outreach.search import run_search, guess_company_name_from_title
from app.job_outreach.email_discovery import (
    research_company, discover_email, gather_company_snippets, gather_contact_snippets,
)
from app.job_outreach.email_generator import generate_application_email
from app.job_outreach.settings_store import (
    is_running, set_running, emails_remaining_today, increment_emails_sent_today,
    set_company_limit, get_company_limit, reset_companies_found_this_run,
    get_companies_found_this_run, increment_companies_found_this_run,
)
from app.utils.ids import new_id
from app.utils.time_utils import iso_now

logger = logging.getLogger("job_outreach.service")


async def _log_activity(event: str, details: str = "") -> None:
    await activity_log_repo.create({
        "log_id": new_id("activity"), "event": event, "details": details, "created_at": iso_now(),
    })


def _normalize(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


async def _already_seen_company(normalized_name: str) -> bool:
    """A company is skipped if it's on the suppression list OR already
    exists in COMPANIES at all (regardless of research outcome) — this
    module sends at most one email per company, ever, across all runs."""
    suppressed = await suppression_repo.find_where(company_name=normalized_name)
    if suppressed:
        return True
    existing = await company_repo.list_all()
    return any(_normalize(c.get("company_name", "")) == normalized_name for c in existing)


async def start(max_companies: int | None = None) -> None:
    """Starts the automation loop. If max_companies is given (e.g. "1" for a
    quick manual test), the loop auto-stops itself as soon as that many NEW
    companies have been processed in this run — no need to remember to press
    Stop. Leave it unset for the normal continuous-loop behavior."""
    from app.job_outreach.scheduler import start_scheduler
    await set_company_limit(max_companies)
    await reset_companies_found_this_run()
    await set_running(True)
    await _log_activity("AUTOMATION_STARTED", f"max_companies={max_companies or 'unlimited'}")
    start_scheduler()


async def stop() -> None:
    """Stops new search cycles from starting. Deliberately does NOT touch
    already-PENDING EMAIL_QUEUE rows — a separate Apps Script queue worker
    keeps sending those independently of this flag."""
    await set_running(False)
    await _log_activity("AUTOMATION_STOPPED")


async def run_one_cycle() -> dict:
    """Runs exactly one (role, city) search across the fixed lists per
    scheduler tick (see scheduler.py for how combos are picked/rotated),
    then discovers + queues an application email for each newly-qualified
    company, up to whatever quota remains today."""
    settings = get_job_outreach_settings()
    remaining = await emails_remaining_today()
    if remaining <= 0:
        logger.info("JOB_OUTREACH: skipped cycle — today's cap already reached")
        return {"skipped": True, "reason": "daily_cap_reached"}

    results_summary = {"companies_found": 0, "emails_queued": 0, "runs": []}
    company_limit = await get_company_limit()

    async def _limit_reached() -> bool:
        if company_limit is None:
            return False
        return await get_companies_found_this_run() >= company_limit

    for job_title in ROLES:
        for city in ALL_LOCATIONS:
            if await emails_remaining_today() <= 0:
                logger.info("JOB_OUTREACH: cap reached mid-cycle, stopping early")
                return results_summary
            if await _limit_reached():
                logger.info("JOB_OUTREACH: company_limit=%d reached, auto-stopping", company_limit)
                await stop()
                return results_summary

            run_record = await search_run_repo.create({
                "run_id": new_id("run"), "job_title": job_title, "city": city,
                "is_remote": city == "Remote (India)" or city not in INDIA_LOCATIONS,
                "results": 0, "qualified": 0, "companies_found": 0, "emails_queued": 0,
                "status": "RUNNING", "started_at": iso_now(), "completed_at": "", "error_message": "",
            })
            run_id = run_record["run_id"]
            try:
                raw_results = await run_search(job_title, city, result_limit=10)
            except Exception:
                logger.exception("JOB_OUTREACH: search failed job_title=%r city=%r", job_title, city)
                await search_run_repo.update(run_id, {"status": "FAILED", "completed_at": iso_now(),
                                                        "error_message": "search failed"})
                continue

            qualified = 0
            companies_found = 0
            emails_queued_this_run = 0

            for raw in raw_results:
                if await emails_remaining_today() <= 0:
                    break
                if await _limit_reached():
                    break

                company_name = guess_company_name_from_title(raw.title)
                if not company_name:
                    continue
                normalized = _normalize(company_name)
                if await _already_seen_company(normalized):
                    continue

                qualified += 1
                await increment_companies_found_this_run(1)

                await job_listing_repo.create({
                    "job_id": new_id("job"), "source": "TAVILY", "job_title": job_title,
                    "company_name": company_name, "location": city, "city": city, "state": "",
                    "country": "India" if city != "Remote (India)" else "India",
                    "is_remote": raw.is_remote, "description": raw.snippet, "job_url": raw.url,
                    "posted_date": "", "run_id": run_id, "created_at": iso_now(),
                })

                company = await company_repo.create({
                    "company_id": new_id("company"), "company_name": company_name,
                    "normalized_name": normalized, "official_website": "", "domain": "",
                    "contact_email": "", "email_type": "", "email_source_url": "",
                    "email_confidence": 0, "research_status": "RESEARCHING",
                    "created_at": iso_now(), "updated_at": iso_now(),
                })
                companies_found += 1

                try:
                    company_snippets = await gather_company_snippets(company_name, city)
                    research = research_company(company_name, city, company_snippets)
                    domain = (research or {}).get("domain")
                    website = (research or {}).get("official_website")

                    contact_snippets = await gather_contact_snippets(company_name, domain)
                    discovered = discover_email(company_name, domain, contact_snippets)
                except Exception:
                    logger.exception("JOB_OUTREACH: research/discovery failed for %r", company_name)
                    await company_repo.update(company["company_id"], {"research_status": "FAILED"})
                    continue

                email_type = (discovered or {}).get("email_type") or "UNKNOWN"
                email = (discovered or {}).get("email")

                if not email or email_type not in ACCEPTED_EMAIL_TYPES:
                    # Same official-email-only filter as the main system:
                    # HR/DEPARTMENT/UNKNOWN (or no email at all) -> drop the
                    # company, same as "no email found".
                    logger.info("JOB_OUTREACH: DROP company=%r reason=non_official_or_missing_email "
                                "email=%s email_type=%s", company_name, email, email_type)
                    await company_repo.update(company["company_id"], {
                        "official_website": website or "", "domain": domain or "",
                        "email_type": email_type, "research_status": "NOT_FOUND",
                    })
                    await suppression_repo.create({
                        "suppression_id": new_id("suppression"), "company_id": company["company_id"],
                        "company_name": normalized, "domain": domain or "", "reason": "INVALID_EMAIL",
                        "created_at": iso_now(),
                    })
                    continue

                await company_repo.update(company["company_id"], {
                    "official_website": website or "", "domain": domain or "",
                    "contact_email": email, "email_type": email_type,
                    "email_source_url": (discovered or {}).get("email_source_url") or "",
                    "email_confidence": (discovered or {}).get("email_confidence") or 0,
                    "research_status": "COMPLETED",
                })

                generated = generate_application_email(
                    job_title=job_title, sender_email=settings.job_outreach_sender_email,
                    company_name=company_name,
                )
                await email_queue_repo.create({
                    "queue_id": new_id("queue"), "company_id": company["company_id"],
                    "job_id": "", "recipient_email": email,
                    "sender_email": settings.job_outreach_sender_email,
                    "subject": generated["subject"], "body": generated["body"], "html_body": "",
                    "status": "PENDING", "attempts": 0, "max_attempts": 3,
                    "scheduled_at": iso_now(), "sent_at": "", "message_id": "", "thread_id": "",
                    "error_message": "", "test_mode": settings.job_outreach_email_test_mode,
                    "created_at": iso_now(), "updated_at": iso_now(),
                })
                await suppression_repo.create({
                    "suppression_id": new_id("suppression"), "company_id": company["company_id"],
                    "company_name": normalized, "domain": domain or "", "reason": "ALREADY_APPLIED",
                    "created_at": iso_now(),
                })
                await increment_emails_sent_today(1)
                emails_queued_this_run += 1

            await search_run_repo.update(run_id, {
                "results": len(raw_results), "qualified": qualified,
                "companies_found": companies_found, "emails_queued": emails_queued_this_run,
                "status": "COMPLETED", "completed_at": iso_now(),
            })
            results_summary["companies_found"] += companies_found
            results_summary["emails_queued"] += emails_queued_this_run
            results_summary["runs"].append(run_id)

            if await _limit_reached():
                logger.info("JOB_OUTREACH: company_limit=%d reached after run %s, auto-stopping",
                            company_limit, run_id)
                await stop()
                return results_summary

    await _log_activity(
        "SEARCH_CYCLE_COMPLETED",
        f"companies_found={results_summary['companies_found']} emails_queued={results_summary['emails_queued']}",
    )
    return results_summary


async def get_status() -> dict:
    from app.job_outreach.settings_store import get_daily_cap, emails_sent_today

    running = await is_running()
    remaining = await emails_remaining_today()
    cap = await get_daily_cap()
    sent_today = await emails_sent_today()
    limit = await get_company_limit()
    found_this_run = await get_companies_found_this_run()
    return {
        "running": running,
        "emails_sent_today": sent_today,
        "daily_cap": cap,
        "emails_remaining_today": remaining,
        "company_limit": limit,
        "companies_found_this_run": found_this_run,
    }
