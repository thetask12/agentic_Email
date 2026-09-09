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

import httpx

from app.config.settings import get_settings
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

# The 9 job platforms this module searches (site-scoped, read-only public
# search results — never a login/scrape of any of these sites, same rule as
# the main system's source_manager.py). Mirrors the old system's
# DAILY_SOURCES list. Each platform gets its own `site:` query per
# (role, city) combination, so results are pulled specifically from that
# platform rather than a generic web search.
PLATFORM_DOMAINS: dict[str, str] = {
    "naukri": "naukri.com",
    "indeed": "indeed.com",
    "linkedin": "linkedin.com/jobs",
    "apna": "apna.co",
    "foundit": "foundit.in",
    "timesjobs": "timesjobs.com",
    "workindia": "workindia.in",
    "shine": "shine.com",
    "internshala": "internshala.com",
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


# Words that show up in a job-listing-aggregator page TITLE rather than a
# real company name, e.g. "AI Engineer Jobs In Bangalore" or "Best AI
# Developer Careers 2026" — a search result whose title is just a generic
# search-results-page description, not a specific employer's posting.
# Matching one of these means "don't trust this as a company name", not
# "this job isn't real" — the listing itself may still be legitimate.
_GENERIC_LISTING_WORDS = {
    "jobs", "job", "careers", "career", "hiring", "openings", "opening",
    "vacancy", "vacancies", "listings", "listing", "search", "results",
}


def _looks_like_generic_listing_title(candidate: str) -> bool:
    """True if `candidate` reads like an aggregator page title (mentions
    role/location/generic-jobs words) rather than a specific company name."""
    words = set(re.findall(r"[a-z]+", candidate.lower()))
    return bool(words & _GENERIC_LISTING_WORDS)


def guess_company_name_from_title(title: str) -> str | None:
    """Best-effort extraction of a company name from a search result title,
    e.g. 'AI Engineer - Acme Labs - LinkedIn' -> 'Acme Labs'. Heuristic only;
    never returns a job-board/platform name or a generic listing-page title
    (e.g. 'AI Engineer Jobs In Bangalore') that isn't actually a company."""
    parts = [p.strip() for p in re.split(r"[-|–]", title) if p.strip()]
    for candidate in parts[1:]:
        if _is_platform_name(candidate):
            continue
        if _looks_like_generic_listing_title(candidate):
            continue
        if 2 < len(candidate) < 80:
            return candidate
    return None


async def fetch_raw_page_content(query: str) -> str:
    """Issues a single Tavily search with include_raw_content=true and
    returns the first result's full page text (or "" if unavailable) —
    used as the input to an AI company-name-extraction pass
    (job_extraction.extract_company_name) when the cheap title-splitting
    heuristic (guess_company_name_from_title) fails, e.g. for a listing
    page whose search-result TITLE is generic ("AI Engineer Jobs In
    Bangalore") but whose actual page body still names a specific employer
    for a specific posting. Same Tavily-index-only, no-login/no-scrape rule
    as everywhere else — this is a plain search API call, not a raw HTTP
    fetch of the page ourselves."""
    settings = get_settings()
    if not settings.tavily_configured:
        return ""
    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 1,
        "include_answer": False,
        "include_raw_content": True,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            if resp.status_code >= 400:
                return ""
            data = resp.json()
    except httpx.HTTPError:
        return ""
    items = data.get("results", []) or []
    if not items:
        return ""
    return (items[0].get("raw_content") or items[0].get("content") or "")[:4000]


def _location_clause(city: str) -> str:
    """The location-qualifying part of a query, shared by every platform's
    site-scoped query for one (role, city) combination."""
    if city == "Remote (India)":
        return "remote India hiring"
    if city in INDIA_LOCATIONS:
        return f'"{city}" hiring'
    # Remote-international: only postings explicitly open to remote/India
    # candidates are relevant — bias the query toward that qualifier so
    # irrelevant on-site-only postings in that country are less likely to
    # dominate results. Final qualification still happens via AI extraction
    # downstream (service.py), this is just query-time steering.
    return f'"{city}" remote India candidates hiring'


def build_queries(job_title: str, city: str) -> list[str]:
    """Construct one site-scoped query per platform in PLATFORM_DOMAINS for
    this (role, city) combination, e.g. 'site:naukri.com "AI Engineer"
    "Bangalore" hiring'. Never a login/scrape of any platform — this is a
    plain public search-engine query restricted to that domain."""
    location_clause = _location_clause(city)
    return [
        f'site:{domain} "{job_title}" {location_clause}'
        for domain in PLATFORM_DOMAINS.values()
    ]


async def run_search(job_title: str, city: str, result_limit: int = 10) -> list[RawJobResult]:
    is_remote = city == "Remote (India)" or city not in INDIA_LOCATIONS
    queries = build_queries(job_title, city)
    logger.info("JOB_OUTREACH_SEARCH_START job_title=%r city=%r platforms=%d",
                job_title, city, len(queries))

    # Split result_limit across the 9 platform queries (at least 1 each) so
    # a single (role, city) combination doesn't return an unbounded number
    # of results just because it now issues 9 queries instead of 1.
    per_platform_limit = max(1, result_limit // len(queries)) if queries else result_limit

    results: list[RawJobResult] = []
    for q in queries:
        hits: list[SearchResult] = await search(q, num=min(per_platform_limit, 10))
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
