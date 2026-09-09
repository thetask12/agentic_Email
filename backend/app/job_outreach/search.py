"""
Tavily-based company/job discovery for the Job Outreach module — reuses the
existing app.integrations.web_search Tavily client (a generic search
provider, safe to share) rather than duplicating it, since it carries no
Botivate-specific state or behavior.

For each (role, city) combination in the fixed lists (app.job_outreach.models
ROLES / ALL_LOCATIONS), issues a general web search query, extracts
candidate company + job postings from the result snippets, and returns them
for the caller (service.py) to dedupe against SUPPRESSION_LIST/COMPANIES and
persist to JOB_LISTINGS.

Same "never bypass login/CAPTCHA/paywalls, never fabricate results" rule as
the main system's source_manager.py — if Tavily is not configured or a query
yields nothing, this returns an empty list, never fake data.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.integrations.web_search import search, SearchResult
from app.job_outreach.models import INDIA_LOCATIONS

logger = logging.getLogger("job_outreach.search")

# Same platform/aggregator-name rejection idea as the main system's
# source_manager.py (guess_company_name_from_title) — never treat a job
# board's own name as the hiring company.
_PLATFORM_NAMES = {
    "naukri", "indeed", "linkedin", "linkedin jobs", "apna", "foundit",
    "timesjobs", "workindia", "shine", "internshala", "google", "jobs",
    "careers", "job", "career", "wellfound", "angellist", "glassdoor",
    "cutshort", "instahyre", "hirist",
}


@dataclass
class RawJobResult:
    title: str
    url: str
    snippet: str
    job_title: str
    city: str
    is_remote: bool


def _is_platform_name(candidate: str) -> bool:
    normalized = re.sub(r"\.(com|in|co)$", "", candidate.strip().lower())
    return normalized in _PLATFORM_NAMES


def guess_company_name_from_title(title: str) -> str | None:
    """Best-effort extraction of a company name from a search result title,
    e.g. 'AI Engineer - Acme Labs - LinkedIn' -> 'Acme Labs'. Heuristic only;
    never returns a job-board/platform name."""
    parts = [p.strip() for p in re.split(r"[-|–]", title) if p.strip()]
    for candidate in parts[1:]:
        if _is_platform_name(candidate):
            continue
        if 2 < len(candidate) < 80:
            return candidate
    return None


def build_queries(job_title: str, city: str) -> list[str]:
    """Construct search queries for one (role, city) combination. India
    cities get an onsite-or-remote query; the fixed "Remote (India)" and
    remote-international entries get a query that requires explicit
    openness to remote/India candidates, since those postings are not
    inherently location-scoped."""
    if city == "Remote (India)":
        return [f'"{job_title}" remote India hiring']
    if city in INDIA_LOCATIONS:
        return [f'"{job_title}" "{city}" hiring']
    # Remote-international: only postings explicitly open to remote/India
    # candidates are relevant — bias the query toward that qualifier so
    # irrelevant on-site-only postings in that country are less likely to
    # dominate results. Final qualification still happens via AI extraction
    # downstream (service.py), this is just query-time steering.
    return [f'"{job_title}" "{city}" remote India candidates hiring']


async def run_search(job_title: str, city: str, result_limit: int = 10) -> list[RawJobResult]:
    is_remote = city == "Remote (India)" or city not in INDIA_LOCATIONS
    queries = build_queries(job_title, city)
    logger.info("JOB_OUTREACH_SEARCH_START job_title=%r city=%r queries=%s", job_title, city, queries)

    results: list[RawJobResult] = []
    for q in queries:
        hits: list[SearchResult] = await search(q, num=min(result_limit, 10))
        logger.info("JOB_OUTREACH_SEARCH_RESULT job_title=%r city=%r query=%r hits=%d",
                    job_title, city, q, len(hits))
        for h in hits:
            results.append(RawJobResult(
                title=h.title, url=h.link, snippet=h.snippet,
                job_title=job_title, city=city, is_remote=is_remote,
            ))

    # De-duplicate by URL within this (role, city) run.
    seen = set()
    deduped = []
    for r in results:
        if r.url in seen:
            continue
        seen.add(r.url)
        deduped.append(r)
    logger.info("JOB_OUTREACH_SEARCH_END job_title=%r city=%r raw=%d deduped=%d",
                job_title, city, len(results), len(deduped))
    return deduped[:result_limit]
