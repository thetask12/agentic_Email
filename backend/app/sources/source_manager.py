"""
Source Manager (System.txt sections 8, 90, 91).

Modular, non-hardcoded source architecture. Each source is a "site:" scoped
web search query construction — we do NOT bypass login/CAPTCHA/paywalls
and we do NOT scrape job portals directly. This respects robots.txt/ToS by
only reading back what is already publicly indexed via the configured
search provider (Tavily — see app/integrations/web_search.py).

If a source's search yields nothing or the provider isn't configured, the
source is marked UNAVAILABLE/BLOCKED in SOURCE_STATUS rather than
fabricating jobs.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.integrations.web_search import search, SearchResult
from app.models.enums import JobSource, SourceStatusValue
from app.repositories.repositories import source_status_repo
from app.utils.time_utils import iso_now

logger = logging.getLogger("source_manager")

SOURCE_DOMAINS: dict[JobSource, str] = {
    JobSource.NAUKRI: "naukri.com",
    JobSource.INDEED: "in.indeed.com",
    JobSource.LINKEDIN: "linkedin.com/jobs",
    JobSource.APNA: "apna.co",
    JobSource.FOUNDIT: "foundit.in",
    JobSource.TIMESJOBS: "timesjobs.com",
    JobSource.WORKINDIA: "workindia.in",
    JobSource.SHINE: "shine.com",
    JobSource.INTERNSHALA: "internshala.com",
}

DISPLAY_NAMES: dict[JobSource, str] = {
    JobSource.NAUKRI: "Naukri",
    JobSource.INDEED: "Indeed",
    JobSource.LINKEDIN: "LinkedIn Jobs",
    JobSource.APNA: "Apna",
    JobSource.FOUNDIT: "Foundit",
    JobSource.TIMESJOBS: "TimesJobs",
    JobSource.WORKINDIA: "WorkIndia",
    JobSource.SHINE: "Shine",
    JobSource.INTERNSHALA: "Internshala",
    JobSource.COMPANY_CAREERS: "Company Career Pages",
    JobSource.GOOGLE_SEARCH: "Google Web Search",
}


@dataclass
class RawJobResult:
    source: str
    title: str
    url: str
    snippet: str


def build_queries(job_title: str, state: str | None, city: str | None, source: JobSource) -> list[str]:
    """Construct site-scoped search queries. Never hardcoded to a single job title."""
    location_terms = [t for t in [city, state] if t]
    location_str = " ".join(f'"{t}"' for t in location_terms)
    base = f'"{job_title}" {location_str}'.strip()

    if source == JobSource.GOOGLE_SEARCH:
        # General discovery: company career pages + broad indexed job postings.
        return [
            f'{base} hiring',
            f'{base} careers job opening',
        ]

    domain = SOURCE_DOMAINS.get(source)
    if not domain:
        return []
    return [f'site:{domain} {base}']


async def run_source(job_title: str, state: str | None, city: str | None, source: JobSource,
                      result_limit: int = 10) -> list[RawJobResult]:
    queries = build_queries(job_title, state, city, source)
    logger.info("SOURCE_RUN_START source=%s queries=%s", source.value, queries)
    if not queries:
        logger.warning("SOURCE_NO_QUERY_STRATEGY source=%s", source.value)
        await _mark_status(source, SourceStatusValue.UNAVAILABLE, "No query strategy configured")
        return []

    results: list[RawJobResult] = []
    any_success = False
    for q in queries:
        hits: list[SearchResult] = await search(q, num=min(result_limit, 10))
        logger.info("SOURCE_QUERY_RESULT source=%s query=%r hits=%d", source.value, q, len(hits))
        if hits:
            any_success = True
        filtered_out = 0
        for h in hits:
            if source != JobSource.GOOGLE_SEARCH:
                domain = SOURCE_DOMAINS.get(source, "")
                if domain.split("/")[0] not in h.link:
                    filtered_out += 1
                    continue
            results.append(RawJobResult(source=source.value, title=h.title, url=h.link, snippet=h.snippet))
        if filtered_out:
            logger.info(
                "SOURCE_DOMAIN_FILTER_DROPPED source=%s query=%r dropped=%d "
                "(hit returned by search but link doesn't contain expected domain)",
                source.value, q, filtered_out,
            )

    if not any_success:
        logger.warning("SOURCE_UNAVAILABLE source=%s reason=no_indexed_results", source.value)
        await _mark_status(source, SourceStatusValue.UNAVAILABLE, "No indexed results returned (search not configured or no matches)")
    else:
        await _mark_status(source, SourceStatusValue.OK, f"{len(results)} results")

    # De-duplicate by URL within this source
    seen = set()
    deduped = []
    for r in results:
        if r.url in seen:
            continue
        seen.add(r.url)
        deduped.append(r)
    logger.info("SOURCE_RUN_END source=%s raw=%d deduped=%d returned=%d",
                source.value, len(results), len(deduped), len(deduped[:result_limit]))
    return deduped[:result_limit]


async def _mark_status(source: JobSource, status: SourceStatusValue, notes: str) -> None:
    existing = await source_status_repo.get_by_id(source.value)
    record = {
        "source": source.value,
        "display_name": DISPLAY_NAMES.get(source, source.value),
        "enabled": True,
        "last_status": status.value,
        "last_checked_at": iso_now(),
        "notes": notes,
    }
    if existing:
        await source_status_repo.update(source.value, record)
    else:
        await source_status_repo.create(record)


# Platform/aggregator names that must never be treated as a hiring company.
# Job board titles frequently place the platform's own name in the same
# "second segment" position a real employer name would occupy (e.g.
# Internshala listings often read "MIS Executive - Internshala" with no
# employer name in the title at all), which previously caused leads to be
# created against "Internshala"/"Naukri" etc. as the company. Any title
# segment matching one of these (case-insensitive, ignoring a trailing
# .com/.in) is rejected rather than accepted as a low-confidence guess.
_PLATFORM_NAMES = {
    "naukri", "indeed", "linkedin", "linkedin jobs", "apna", "foundit",
    "timesjobs", "workindia", "shine", "internshala", "google", "jobs",
    "careers", "job", "career",
}


def is_platform_name(candidate: str) -> bool:
    normalized = re.sub(r"\.(com|in|co)$", "", candidate.strip().lower())
    return normalized in _PLATFORM_NAMES


def guess_company_name_from_title(title: str) -> str | None:
    """Best-effort extraction of a company name from a search result title,
    e.g. 'MIS Executive - ABC Pvt Ltd - Naukri.com' -> 'ABC Pvt Ltd'.
    This is a heuristic only; low-confidence extractions should be confirmed
    by the JobExtraction AI agent from the full snippet/description. Never
    returns a job-board/platform name — see _PLATFORM_NAMES above."""
    parts = [p.strip() for p in re.split(r"[-|–]", title) if p.strip()]
    for candidate in parts[1:]:  # skip parts[0], which is the job title itself
        if is_platform_name(candidate):
            continue
        if 2 < len(candidate) < 80:
            return candidate
    return None
