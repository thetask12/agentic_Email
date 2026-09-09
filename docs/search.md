# Web Search Setup (Job Discovery)

The Source Manager (`backend/app/sources/source_manager.py`) never scrapes
job portals directly — it only issues site-scoped queries against a search
index and reads back publicly indexed results. This respects robots.txt/
ToS/anti-bot systems (System.txt rule #8).

Job discovery uses **Tavily Search** (`backend/app/integrations/web_search.py`).

## 1. Get a Tavily API key
1. Go to https://tavily.com and sign up.
2. Copy your API key from the dashboard.
3. Put it in `TAVILY_API_KEY` (backend `.env` / Render environment
   variables).

## How queries are built
`source_manager.build_queries()` constructs one or more site-scoped queries
per source per search (e.g.
`site:naukri.com "MIS Executive" "Raipur" "Chhattisgarh"`), scoped to the
user's selected job title/city/state — never a worldwide, unscoped search
when a location filter is set (rule #89-91). For the `google_search` source
entry (general discovery beyond a single job board), broader queries like
`"MIS Executive" "Raipur" hiring` are used instead of a `site:` filter.

## Behavior when not configured
If `TAVILY_API_KEY` is empty, `web_search.search()` returns an empty list
and the affected source is marked `UNAVAILABLE` in `SOURCE_STATUS` — the
search run continues with whatever other sources are configured, and never
fabricates results.

## Quotas
Tavily's free tier includes 1,000 searches/month, well above what Google's
Custom Search JSON API offered (100 queries/day) for the same per-run query
volume. Each source × each search run issues 1-2 queries, so a run across
all 9 sources uses roughly 10-15 Tavily searches.

## Migrated from Google Custom Search
This system previously used Google's Custom Search JSON API. It was
replaced after persistent `403 Forbidden` responses in production (caused
by Cloud Console configuration — API not enabled / billing not linked / key
restrictions blocking server-side calls) and because its 100-queries/day
free cap was too restrictive for repeated site-scoped queries across 9
sources. The old `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` settings
are still accepted (so old `.env` files don't break config parsing) but are
no longer read by any code path — safe to leave blank or delete.
