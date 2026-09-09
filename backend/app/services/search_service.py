"""
Search orchestration (System.txt sections 7, 92-95, 138 end-to-end flow).

Pipeline per search run:
  sources -> raw results -> JobExtraction -> location filter -> dedup
  -> COMPANIES upsert -> CompanyResearch -> EmailDiscovery -> CONTACTS
  -> LEADS -> OpportunityAnalysis -> lead score -> EMAIL_DRAFTS -> auto-queued
  immediately (per explicit user instruction: no manual approval step -
  every drafted email is queued the moment it's generated, one lead at a
  time, rather than waiting for the whole run to finish or requiring a
  human click). EMAIL_TEST_MODE stays the actual safety net: Apps Script
  still redirects every real send to TEST_EMAIL regardless of this.

Every step publishes a real event to the EventBus — no fake progress
numbers (rule 94). If a step fails or a source is unavailable, the run
continues with the remaining sources/steps.
"""
from __future__ import annotations

import logging

from app.models.enums import (
    JobSource, ResearchStatus, LeadStatus, EmailDraftStatus, RecommendedSolution,
    SearchRunStatus, VerificationStatus, EmailType,
)
from app.repositories.repositories import (
    search_run_repo, job_repo, company_repo, contact_repo, lead_repo, email_draft_repo,
    email_template_repo, email_queue_repo,
)
from app.sources.source_manager import run_source, guess_company_name_from_title, is_platform_name
from app.agents.job_extraction import extract_job
from app.agents.company_research import (
    research_company, discover_email, gather_company_snippets, gather_contact_snippets,
)
from app.agents.opportunity_analysis import analyze_opportunity, compute_lead_score, compute_priority
from app.agents.email_generation import generate_initial_email
from app.services.activity_service import log_activity
from app.services.email_queue_service import queue_email
from app.services.event_bus import event_bus
from app.services.search_cancellation import is_cancelled, clear as clear_cancellation
from app.utils.ids import new_id
from app.utils.location import normalize_state, normalize_city, city_in_state
from app.utils.time_utils import iso_now
from app.config.settings import get_settings

logger = logging.getLogger("search_service")


async def start_search(*, job_title: str, state: str | None, city: str | None,
                        date_filter: str, experience: str | None, sources: list[str],
                        result_limit: int) -> dict:
    run_id = new_id("run")
    norm_state = normalize_state(state) if state else None
    norm_city = normalize_city(city) if city else None
    record = {
        "run_id": run_id,
        "query": job_title,
        "job_title": job_title,
        "state": norm_state or "",
        "city": norm_city or "",
        "sources": ",".join(sources),
        "date_filter": date_filter,
        "experience": experience or "",
        "result_limit": result_limit,
        "results": 0,
        "qualified": 0,
        "companies": 0,
        "emails": 0,
        "leads": 0,
        "status": SearchRunStatus.PENDING.value,
        "started_at": iso_now(),
        "completed_at": "",
        "error_message": "",
    }
    await search_run_repo.create(record)
    return record


async def execute_search(run_id: str) -> None:
    settings = get_settings()
    run = await search_run_repo.get_by_id(run_id)
    if not run:
        logger.error("Search run %s not found", run_id)
        return

    await search_run_repo.update(run_id, {"status": SearchRunStatus.RUNNING.value})
    await event_bus.publish(run_id, "search_progress", {"status": "RUNNING", "message": "Search started"})

    job_title = run["job_title"]
    state = run.get("state") or None
    city = run.get("city") or None
    # target_lead_count is a target for actual outreach-ready LEADS (i.e.
    # a company where a public email was also found), not raw jobs — per
    # explicit user instruction, the run keeps working through sources
    # until this many leads exist or every source is exhausted, rather
    # than stopping after the first pass over each source regardless of
    # how many of those results turned into real leads.
    target_lead_count = int(run.get("result_limit") or 10)
    # Per-source fetch size is now independent of the lead target — a
    # generous fixed cap so each source is queried for as much as it can
    # give in one pass (still bounded, to avoid unbounded quota usage on a
    # single search/agent provider), while target_lead_count is what
    # actually decides when the run stops.
    per_source_fetch_limit = 30
    sources = [s for s in (run.get("sources") or "").split(",") if s]

    total_results = 0
    qualified_count = 0
    company_count = 0
    email_count = 0
    lead_count = 0
    seen_urls: set[str] = set()

    # In-memory caches for the duration of this run only. The Google Sheets
    # API has a default quota of 60 read requests/minute/user — without
    # this cache, every job result triggers a fresh full-sheet
    # find_one_where() lookup against COMPANIES and CONTACTS, which blows
    # the quota within seconds on any real result set and silently starves
    # the rest of the run (or fails it outright with a 429). Companies and
    # contacts created by earlier iterations of this same run are looked up
    # here first; only a genuine cache miss falls through to the Sheet.
    company_cache: dict[str, dict] = {}
    contact_cache: dict[str, dict | None] = {}

    # Every recipient address that has EVER had an outreach email
    # drafted/sent for them, across ALL search runs (not just this one).
    # This is the actual duplicate-send guard: the same company/contact can
    # legitimately turn up again in a later search (same company posts
    # another job, or the same role search overlaps), and without this
    # check that would create a brand new lead + a brand new EMAIL_DRAFTS
    # row + auto-queue it — i.e. a second cold email to someone who was
    # already contacted. A company/contact record being reused (via
    # company_cache/contact_cache above) is fine; creating a NEW lead and
    # sending them ANOTHER initial email is not.
    existing_drafts = await email_draft_repo.list_all()
    already_emailed: set[str] = {
        str(d.get("recipient_email", "")).strip().lower()
        for d in existing_drafts if d.get("recipient_email")
    }

    default_template = await _get_default_template()
    logger.info("RUN_%s: default_template=%s", run_id,
                default_template.get("template_id") if default_template else "NONE FOUND")

    cancelled = False
    target_reached = False
    for source_name in sources:
        if is_cancelled(run_id):
            logger.info("RUN_%s: cancellation requested, stopping before source=%s", run_id, source_name)
            cancelled = True
            break
        if lead_count >= target_lead_count:
            logger.info("RUN_%s: target_lead_count=%d reached before source=%s, stopping",
                        run_id, target_lead_count, source_name)
            target_reached = True
            break
        try:
            source_enum = JobSource(source_name)
        except ValueError:
            continue

        raw_results = await run_source(job_title, state, city, source_enum, per_source_fetch_limit)
        logger.info("RUN_%s: source=%s returned %d raw results", run_id, source_name, len(raw_results))
        await event_bus.publish(run_id, "source_status", {
            "source": source_name, "found": len(raw_results),
        })

        for raw in raw_results:
            if is_cancelled(run_id):
                logger.info("RUN_%s: cancellation requested, stopping mid-source=%s", run_id, source_name)
                cancelled = True
                break
            if lead_count >= target_lead_count:
                logger.info("RUN_%s: target_lead_count=%d reached mid-source=%s, stopping",
                            run_id, target_lead_count, source_name)
                target_reached = True
                break
            if raw.url in seen_urls:
                logger.debug("RUN_%s: skip duplicate url=%s", run_id, raw.url)
                continue
            seen_urls.add(raw.url)
            total_results += 1

            extracted = extract_job(raw.title, raw.snippet, raw.url, job_title)
            if not extracted:
                logger.warning("RUN_%s: DROP url=%s reason=job_extraction_returned_none "
                                "(OpenAI not configured or call failed)", run_id, raw.url)
                continue
            if not extracted.get("is_relevant_role"):
                logger.info("RUN_%s: DROP url=%s reason=not_relevant_role title=%r",
                            run_id, raw.url, raw.title)
                continue

            ai_company_name = extracted.get("company_name")
            if ai_company_name and is_platform_name(ai_company_name):
                logger.info("RUN_%s: IGNORE ai_company_name=%r (looks like a job-board/platform "
                            "name, not a real employer) url=%s", run_id, ai_company_name, raw.url)
                ai_company_name = None
            company_name = ai_company_name or guess_company_name_from_title(raw.title)
            if not company_name:
                logger.warning("RUN_%s: DROP url=%s reason=no_company_name_extracted title=%r",
                               run_id, raw.url, raw.title)
                continue

            job_city = extracted.get("city") or city
            job_state = extracted.get("state") or state
            if state and job_state and not city_in_state(job_city, job_state):
                if normalize_state(job_state) != normalize_state(state):
                    logger.info("RUN_%s: DROP url=%s reason=location_mismatch job_state=%r requested_state=%r",
                                run_id, raw.url, job_state, state)
                    continue

            job_id = new_id("job")
            job_record = {
                "job_id": job_id,
                "source": source_name,
                "source_job_id": "",
                "job_title": extracted.get("job_title") or job_title,
                "company_id": "",
                "company_name": company_name,
                "location": f"{job_city or ''}, {job_state or ''}".strip(", "),
                "city": job_city or "",
                "state": job_state or "",
                "country": "India",
                "description": raw.snippet,
                "experience": extracted.get("experience") or "",
                "salary": extracted.get("salary") or "",
                "employment_type": extracted.get("employment_type") or "",
                "posted_date": "",
                "skills": ",".join(extracted.get("skills") or []),
                "qualification": extracted.get("qualification") or "",
                "job_url": raw.url,
                "application_url": raw.url,
                "source_url": raw.url,
                "extraction_confidence": extracted.get("extraction_confidence", 0),
                "run_id": run_id,
                "is_qualified": True,
                "created_at": iso_now(),
            }
            qualified_count += 1
            await event_bus.publish(run_id, "job_found", {"job_id": job_id, "company_name": company_name,
                                                            "job_title": job_record["job_title"], "source": source_name})

            company_key = company_name.strip().lower()
            company = company_cache.get(company_key)
            if company is None and company_key not in company_cache:
                company = await company_repo.find_one_where(normalized_name=company_key)
                if company:
                    company_cache[company_key] = company

            if not company:
                company_id = new_id("company")
                company_record = {
                    "company_id": company_id, "company_name": company_name,
                    "normalized_name": company_key, "official_website": "", "domain": "",
                    "industry": "", "city": job_city or "", "state": job_state or "",
                    "country": "India", "phone": "", "linkedin_url": "",
                    "company_description": "", "website_confidence": 0,
                    "research_status": ResearchStatus.PENDING.value,
                }
                company = await company_repo.create(company_record)
                company_cache[company_key] = company
                company_count += 1
                await event_bus.publish(run_id, "company_found", {"company_id": company_id, "company_name": company_name})

                snippets = await gather_company_snippets(company_name, job_city, job_state)
                research = research_company(company_name, job_city, job_state, snippets)
                if research:
                    await company_repo.update(company_id, {
                        "official_website": research.get("official_website") or "",
                        "domain": research.get("domain") or "",
                        "industry": research.get("industry") or "",
                        "company_description": research.get("company_description") or "",
                        "linkedin_url": research.get("linkedin_url") or "",
                        "phone": research.get("phone") or "",
                        "website_confidence": research.get("website_confidence", 0),
                        "research_status": ResearchStatus.COMPLETED.value,
                    })
                    company["domain"] = research.get("domain") or ""
                    company["website_confidence"] = research.get("website_confidence", 0)
                else:
                    await company_repo.update(company_id, {"research_status": ResearchStatus.FAILED.value})
                await log_activity(lead_id=None, company_id=company_id, activity_type="COMPANY_RESEARCHED",
                                    description=f"Researched {company_name}")

            company_id = company["company_id"]
            job_record["company_id"] = company_id
            await job_repo.create(job_record)

            if company_id in contact_cache:
                contact = contact_cache[company_id]
            else:
                contact = await contact_repo.find_one_where(company_id=company_id)
                if not contact:
                    contact_snippets = await gather_contact_snippets(company_name, company.get("domain"))
                    discovered = discover_email(company_name, company.get("domain"), contact_snippets)
                    # Only accept the company's own general/official email
                    # (GENERIC) or a named founder/owner email (FOUNDER) as
                    # the outreach target — per explicit user instruction,
                    # HR/careers/support department inboxes are not the
                    # right recipient for this cold-outreach pitch, even
                    # when discover_email() does find one and returns it
                    # with high confidence.
                    accepted_email_types = (EmailType.GENERIC.value, EmailType.FOUNDER.value)
                    if discovered and discovered.get("email") and discovered.get("email_type") not in accepted_email_types:
                        logger.info("RUN_%s: DROP company=%r reason=non_official_email_type "
                                    "email=%s email_type=%s (HR/department inboxes are not accepted "
                                    "as the outreach recipient)",
                                    run_id, company_name, discovered.get("email"), discovered.get("email_type"))
                        discovered = None
                    if discovered and discovered.get("email"):
                        contact_id = new_id("contact")
                        contact = await contact_repo.create({
                            "contact_id": contact_id, "company_id": company_id,
                            "contact_name": discovered.get("contact_name") or "",
                            "designation": discovered.get("designation") or "",
                            "email": discovered["email"],
                            "email_type": discovered.get("email_type") or EmailType.UNKNOWN.value,
                            "email_source_url": discovered.get("email_source_url") or "",
                            "email_confidence": discovered.get("email_confidence", 0),
                            "phone": "", "linkedin_url": "",
                            "verification_status": VerificationStatus.UNVERIFIED.value,
                        })
                        email_count += 1
                        await event_bus.publish(run_id, "email_found", {"company_id": company_id, "email": discovered["email"]})
                        await log_activity(lead_id=None, company_id=company_id, activity_type="EMAIL_FOUND",
                                            description=f"Business email found: {discovered['email']}")
                    else:
                        contact = None
                contact_cache[company_id] = contact

            if not contact:
                logger.warning("RUN_%s: DROP url=%s company=%r reason=no_public_email_found "
                               "(cannot create outreach-ready lead without a verified email)",
                               run_id, raw.url, company_name)
                continue  # No public email found — cannot create an outreach-ready lead.

            recipient_email_lower = str(contact.get("email", "")).strip().lower()
            if recipient_email_lower and recipient_email_lower in already_emailed:
                logger.info("RUN_%s: DROP url=%s company=%r reason=already_emailed email=%s "
                            "(an outreach email already exists for this address from a prior lead/run — "
                            "never send a second initial email to the same recipient)",
                            run_id, raw.url, company_name, contact["email"])
                continue

            opportunity = analyze_opportunity(job_record["job_title"], raw.snippet, extracted.get("skills") or [])
            if opportunity is None:
                logger.warning("RUN_%s: opportunity_analysis_failed url=%s company=%r — "
                               "scoring this lead as 0/MANUAL_REVIEW (OpenAI call failed)",
                               run_id, raw.url, company_name)
            opp_score = opportunity.get("automation_opportunity_score", 0) if opportunity else 0
            signals = opportunity.get("automation_signals", []) if opportunity else []
            pains = opportunity.get("pain_points", []) if opportunity else []
            solution = opportunity.get("recommended_solution", RecommendedSolution.MANUAL_REVIEW.value) if opportunity else RecommendedSolution.MANUAL_REVIEW.value

            lead_score = compute_lead_score(
                opp_score, True, contact.get("email_confidence", 0),
                company.get("website_confidence", 0), extracted.get("extraction_confidence", 0),
            )
            priority = compute_priority(lead_score, opp_score)

            lead_id = new_id("lead")
            lead_record = {
                "lead_id": lead_id, "company_id": company_id, "job_id": job_id,
                "contact_id": contact["contact_id"], "lead_score": lead_score,
                "botivate_opportunity_score": opp_score,
                "automation_signals": ",".join(signals), "pain_points": ",".join(pains),
                "recommended_solution": solution, "priority": priority,
                "status": LeadStatus.QUALIFIED.value, "owner": "",
                "next_action": "FOLLOW_UP", "next_action_date": "",
                "notes": "", "last_activity_at": iso_now(),
            }
            await lead_repo.create(lead_record)
            lead_count += 1
            await event_bus.publish(run_id, "lead_created", {"lead_id": lead_id, "company_id": company_id,
                                                               "lead_score": lead_score, "priority": priority})
            await log_activity(lead_id=lead_id, company_id=company_id, activity_type="STATUS_CHANGED",
                                description=f"Lead qualified — opportunity score {opp_score}")

            if not default_template:
                logger.warning("RUN_%s: SKIP_EMAIL_GENERATION lead_id=%s reason=no_default_template "
                               "(EMAIL_TEMPLATES has no row with is_default=True)", run_id, lead_id)
            else:
                try:
                    generated = generate_initial_email(
                        company_name=company_name, job_title=job_record["job_title"],
                        city=job_city, contact_name=contact.get("contact_name") or None,
                        automation_signals=signals, pain_points=pains,
                        sender_name=settings.botivate_sender_name,
                        botivate_website=settings.botivate_website_url,
                        autorocket_website=settings.autorocket_website_url,
                    )
                    email_id = new_id("email")
                    draft = await email_draft_repo.create({
                        "email_id": email_id, "lead_id": lead_id, "company_id": company_id,
                        "template_id": default_template.get("template_id", ""),
                        "recipient_email": contact["email"],
                        "sender_email": settings.botivate_sender_email,
                        "subject": generated["subject"],
                        "plain_text_body": generated["plain_text_body"],
                        "html_body": generated["html_body"],
                        "personalization_points": ",".join(generated["personalization_points"]),
                        "facts_used": ",".join(generated["facts_used"]),
                        "confidence": generated["confidence"],
                        "status": EmailDraftStatus.DRAFT.value,
                    })
                    # Mark this recipient as emailed immediately so a later
                    # result in THIS SAME run (e.g. the same company posted
                    # two job ads) can't also slip past the already_emailed
                    # check above before the next full sheet read would see it.
                    if recipient_email_lower:
                        already_emailed.add(recipient_email_lower)
                    await lead_repo.update(lead_id, {"status": LeadStatus.EMAIL_DRAFTED.value})
                    await event_bus.publish(run_id, "email_generated", {"lead_id": lead_id, "email_id": email_id})
                    await log_activity(lead_id=lead_id, company_id=company_id, activity_type="EMAIL_GENERATED",
                                        description="Personalized outreach email generated")

                    # Auto-queue immediately (per explicit user instruction: no
                    # manual approval popup — every drafted email is queued as
                    # soon as it's generated, not batched until the search
                    # finishes). EMAIL_TEST_MODE stays on, so Apps Script still
                    # redirects the actual send to TEST_EMAIL — this only
                    # removes the human approval step, not the test-mode
                    # safety net. queue_email() still runs its own suppression
                    # check before making anything sendable.
                    try:
                        await email_draft_repo.update(email_id, {"status": EmailDraftStatus.APPROVED.value})
                        draft["status"] = EmailDraftStatus.APPROVED.value
                        await queue_email(draft)
                        await event_bus.publish(run_id, "email_queued", {"lead_id": lead_id, "email_id": email_id})
                    except Exception:
                        logger.exception("RUN_%s: AUTO_QUEUE_FAILED lead_id=%s email_id=%s",
                                          run_id, lead_id, email_id)
                except Exception:
                    # A failure here (e.g. a transient Sheets error) must not
                    # silently leave a lead with status=QUALIFIED forever, and
                    # must not be swallowed without a trace — log it with the
                    # full stack trace and let the run continue with the rest
                    # of the results, exactly like every other per-job failure
                    # mode in this loop.
                    logger.exception("RUN_%s: EMAIL_GENERATION_FAILED lead_id=%s company=%r",
                                      run_id, lead_id, company_name)

            # Persist SEARCH_RUNS progress counters periodically rather than
            # after every single job — each update() is a Sheets read+write,
            # and doing it per-job is what exhausts the API quota on runs
            # with more than a handful of results. Live progress in the UI
            # still comes from the EventBus (SSE), which this loop already
            # publishes to on every job/company/email/lead — this counter
            # sync is only for the SEARCH_RUNS row itself (used by anyone
            # loading /search/{run_id} without an active SSE connection).
            if qualified_count % 5 == 0:
                await search_run_repo.update(run_id, {
                    "results": total_results, "qualified": qualified_count, "companies": company_count,
                    "emails": email_count, "leads": lead_count,
                })

        if cancelled or target_reached:
            break

    if cancelled:
        # search_routes.stop_search() already sets status=CANCELLED and
        # publishes the final event — this function just needs to stop
        # touching the run further and let that be the last word. Clear the
        # in-memory cancellation flag now that we've honored it, so the
        # run_id can be reused safely if it's ever retried.
        clear_cancellation(run_id)
        logger.info("RUN_%s: stopped by user request after results=%d qualified=%d leads=%d",
                     run_id, total_results, qualified_count, lead_count)
        return

    # Completed either because target_lead_count was reached, or every
    # configured source was exhausted without reaching it — per explicit
    # user instruction, we never loop indefinitely or invent extra query
    # variations to force the count; whatever was genuinely found is final.
    if lead_count < target_lead_count:
        logger.info("RUN_%s: all sources exhausted with leads=%d short of target_lead_count=%d — "
                    "this is the true number of outreach-ready leads available for this "
                    "role/state combination, not a bug", run_id, lead_count, target_lead_count)

    logger.info(
        "RUN_%s: COMPLETED sources=%s results=%d qualified=%d companies=%d emails=%d leads=%d "
        "(target_lead_count=%d openai_configured=%s tavily_configured=%s)",
        run_id, sources, total_results, qualified_count, company_count, email_count, lead_count,
        target_lead_count, settings.openai_configured, settings.tavily_configured,
    )
    await search_run_repo.update(run_id, {
        "status": SearchRunStatus.COMPLETED.value, "completed_at": iso_now(),
        "results": total_results, "qualified": qualified_count, "companies": company_count,
        "emails": email_count, "leads": lead_count,
    })
    await event_bus.publish(run_id, "search_progress", {
        "status": "COMPLETED", "results": total_results, "qualified": qualified_count,
        "companies": company_count, "emails": email_count, "leads": lead_count,
    })
    await event_bus.close(run_id)


async def cancel_run_pending_emails(run_id: str) -> int:
    """Cancels every EMAIL_QUEUE row still PENDING (not yet picked up by
    Apps Script) that belongs to a lead created by this search run. Called
    from POST /api/search/{run_id}/stop.

    EMAIL_QUEUE rows only carry lead_id, not run_id directly, so this walks
    lead_id -> LEADS.job_id -> JOBS.run_id to find the matching leads. This
    is a few full-sheet reads, which is fine here since it only runs once
    per Stop click, not in a hot loop."""
    jobs = await job_repo.find_where(run_id=run_id)
    job_ids = {j["job_id"] for j in jobs}
    if not job_ids:
        return 0

    all_leads = await lead_repo.list_all()
    lead_ids_for_run = {l["lead_id"] for l in all_leads if l.get("job_id") in job_ids}
    if not lead_ids_for_run:
        return 0

    queue_rows = await email_queue_repo.list_all()
    cancelled = 0
    for row in queue_rows:
        if row.get("lead_id") in lead_ids_for_run and row.get("status") == "PENDING":
            await email_queue_repo.update(row["queue_id"], {
                "status": "CANCELLED",
                "error_message": "Cancelled — search run was stopped by the user before this email was sent.",
            })
            cancelled += 1
    return cancelled


async def _get_default_template() -> dict | None:
    templates = await email_template_repo.find_where(is_default=True)
    return templates[0] if templates else None
