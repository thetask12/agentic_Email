"""
Tavily Search API client used for job discovery via Web Search / Discovery
(System.txt sections 8, 89-91).

We never scrape behind login/CAPTCHA/paywalls. We only issue search queries
against Tavily's index (itself index/crawl-based, not a bypass of any
site's auth/anti-bot controls) and read back publicly available results.
If not configured, callers receive an empty list plus a note — never fake
results (rule 94: "No fake progress").

Replaces the prior Google Custom Search integration (see git history /
docs/search.md) after Google's Custom Search JSON API returned persistent
403 Forbidden responses in production (Cloud Console configuration issue:
API not enabled / billing not linked / key restrictions) and its 100
free-queries/day cap was too low for repeated site-scoped queries across
9 sources. Tavily is purpose-built for this exact "AI agent issues many
targeted queries" use case, with a much higher free tier and no per-site
CSE scoping to misconfigure.
"""
from __future__ import annotations

import logging

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("web_search")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class SearchResult:
    def __init__(self, title: str, link: str, snippet: str):
        self.title = title
        self.link = link
        self.snippet = snippet

    def to_dict(self) -> dict:
        return {"title": self.title, "link": self.link, "snippet": self.snippet}


async def search(query: str, num: int = 10) -> list[SearchResult]:
    settings = get_settings()
    if not settings.tavily_configured:
        logger.warning(
            "TAVILY_NOT_CONFIGURED query=%r (TAVILY_API_KEY set=%s) — returning no results",
            query, bool(settings.tavily_api_key),
        )
        return []

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": min(num, 20),
        "include_answer": False,
        "include_raw_content": False,
    }
    logger.info("TAVILY_SEARCH_REQUEST query=%r max_results=%s", query, payload["max_results"])
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(TAVILY_SEARCH_URL, json=payload)
            if resp.status_code == 429:
                logger.warning("TAVILY_RATE_LIMITED query=%r body=%s", query, resp.text[:500])
                return []
            if resp.status_code >= 400:
                # Log the full response body — this is where key/plan issues
                # (invalid key, quota exceeded, credits exhausted) actually
                # show up. A bare raise_for_status() throws this away.
                logger.error(
                    "TAVILY_HTTP_ERROR query=%r status=%s body=%s",
                    query, resp.status_code, resp.text[:1000],
                )
                resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.error("TAVILY_REQUEST_FAILED query=%r error=%s", query, exc)
        return []

    items = data.get("results", []) or []
    logger.info("TAVILY_SEARCH_RESPONSE query=%r items_returned=%d", query, len(items))
    if not items:
        logger.warning("TAVILY_ZERO_RESULTS query=%r full_response=%s", query, str(data)[:1000])
    return [
        SearchResult(i.get("title", ""), i.get("url", ""), i.get("content", ""))
        for i in items
    ]
