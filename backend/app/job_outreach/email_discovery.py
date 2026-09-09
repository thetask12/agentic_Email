"""
Company research + official-email discovery for the Job Outreach module —
same two-agent pattern as app/agents/company_research.py (research_company +
discover_email), reusing the shared app.integrations.openai_client
structured_completion() and app.integrations.web_search.search() helpers
(both generic, provider-level integrations safe to share across modules).

PRIMARY discovery path is now fetch_emails_from_website(): once
research_company() has confidently identified a company's actual official
website, this reads that site's own pages directly (homepage, /contact,
/about, /careers — a plain public GET, never a login/scrape of gated
content) and extracts any visible email addresses with a regex. This is far
more reliable than guessing an email from generic search-result snippets
(the previous sole approach), which was occasionally matching an email from
a completely unrelated page (e.g. a YouTube video that happened to mention
the company's name) to the wrong company. discover_email() (the
snippet-based AI classifier) is kept as a fallback for when the website
fetch finds no email at all.

Same official-email-only filter rule as the main system: only email_type
GENERIC or FOUNDER are ever accepted as an outreach recipient — see
app.job_outreach.models.ACCEPTED_EMAIL_TYPES and service.py, which is where
the actual accept/reject decision is enforced (this module only classifies).
"""
from __future__ import annotations

import logging
import re

import httpx

from app.integrations.openai_client import structured_completion
from app.integrations.web_search import search

logger = logging.getLogger("job_outreach.email_discovery")

# Common paths, tried in order, most-likely-to-list-a-contact-email first.
_CONTACT_PATHS = ["", "/contact", "/contact-us", "/about", "/about-us", "/careers"]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Emails that are clearly not a real business contact even though they match
# the regex — placeholder/example addresses that show up in boilerplate
# templates, tracking pixels, etc.
_JUNK_EMAIL_PATTERNS = (
    "example.com", "yourdomain", "domain.com", "sentry.io", "wixpress.com",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
)


def _is_junk_email(email: str) -> bool:
    lowered = email.lower()
    return any(p in lowered for p in _JUNK_EMAIL_PATTERNS)

COMPANY_SCHEMA = {
    "type": "object",
    "properties": {
        "official_website": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
        "website_confidence": {"type": "number"},
    },
    "required": ["official_website", "domain", "website_confidence"],
    "additionalProperties": False,
}

COMPANY_SYSTEM_PROMPT = """You research a company using ONLY the provided search result
snippets (title, link, snippet for several web search hits about the
company). Identify which result (if any) is the company's own official
website versus a directory/aggregator/unrelated company with a similar
name. Do not fabricate a website or domain that isn't supported by the
snippets. If uncertain, set the field to null and lower
website_confidence. website_confidence is 0-1."""

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "email": {"type": ["string", "null"]},
        "email_type": {"type": "string", "enum": ["GENERIC", "HR", "FOUNDER", "DEPARTMENT", "UNKNOWN"]},
        "email_source_url": {"type": ["string", "null"]},
        "email_confidence": {"type": "number"},
    },
    "required": ["email", "email_type", "email_source_url", "email_confidence"],
    "additionalProperties": False,
}

EMAIL_SYSTEM_PROMPT = """You extract a genuinely publicly-visible official business email address
for a company from the provided search snippets only (e.g. text from a
Contact Us page, About page, or footer that a search engine has indexed).
Rules:
- NEVER invent or guess an email address (e.g. never construct
  info@<domain> unless that literal string appears in the source text).
- Classify the email_type strictly:
  - GENERIC: a general company inbox (info@, contact@, hello@, etc.)
  - FOUNDER: a named founder/owner/CEO's own email, explicitly identified
    as such in the source text
  - HR: a recruiting/HR/careers/jobs inbox
  - DEPARTMENT: any other specific department (sales@, support@, etc.)
  - UNKNOWN: cannot tell, or no email found
- If no email is visible in the provided text, return email=null,
  email_type="UNKNOWN", email_confidence=0.
- Never return a personal/private email not clearly published as a
  business contact."""


def research_company(company_name: str, city: str | None, search_snippets: list[dict]) -> dict | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nLocation: {city or ''}\n\n"
        f"Search results:\n{context}\n\nIdentify the official website and domain."
    )
    return structured_completion(
        system_prompt=COMPANY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=COMPANY_SCHEMA,
        schema_name="job_outreach_company_research",
    )


def discover_email(company_name: str, domain: str | None, search_snippets: list[dict]) -> dict | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"Search results (contact/about pages):\n{context}\n\nExtract and classify a public official email if present."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=EMAIL_SCHEMA,
        schema_name="job_outreach_email_discovery",
    )


async def fetch_emails_from_website(domain: str) -> list[str]:
    """Fetches the company's own homepage plus a few common pages
    (/contact, /about, /careers) and extracts any visible email addresses
    via regex. Plain public GET requests only — no login, no scraping behind
    auth/CAPTCHA, same rule as everywhere else in this system. Returns a
    deduplicated list (order preserved, homepage-first) of candidate emails,
    or an empty list if the site is unreachable or none are found — never
    raises, since a single company's site being down shouldn't crash the
    whole search cycle."""
    if not domain:
        return []
    found: list[str] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; JobOutreachBot/1.0)"}) as client:
        for path in _CONTACT_PATHS:
            for scheme in ("https://", "http://"):
                url = f"{scheme}{domain}{path}"
                try:
                    resp = await client.get(url)
                except httpx.HTTPError:
                    continue
                if resp.status_code >= 400:
                    continue
                for match in _EMAIL_RE.findall(resp.text):
                    if _is_junk_email(match) or match.lower() in seen:
                        continue
                    seen.add(match.lower())
                    found.append(match)
                break  # https worked (or returned a real response) — skip http fallback for this path
            if len(found) >= 5:
                break  # enough candidates gathered — no need to keep crawling more pages
    logger.info("JOB_OUTREACH_WEBSITE_FETCH domain=%r emails_found=%d", domain, len(found))
    return found


def classify_emails(company_name: str, domain: str | None, candidate_emails: list[str]) -> dict | None:
    """AI-classifies a short list of emails actually found on the company's
    own website (via fetch_emails_from_website) into the same
    {email, email_type, email_source_url, email_confidence} shape as
    discover_email(), picking the single best one to use as the outreach
    recipient. Far more reliable than discover_email() because every
    candidate is a real address that was actually present on the company's
    own site, not inferred from a search snippet."""
    if not candidate_emails:
        return None
    listing = "\n".join(f"- {e}" for e in candidate_emails)
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"Email addresses found on this company's own website:\n{listing}\n\n"
        f"Pick the single best one to use as an outreach contact and classify it."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=EMAIL_SCHEMA,
        schema_name="job_outreach_email_classification",
    )


async def gather_company_snippets(company_name: str, city: str | None) -> list[dict]:
    location = city or ""
    results = await search(f'"{company_name}" {location} official website', num=6)
    return [r.to_dict() for r in results]


async def gather_contact_snippets(company_name: str, domain: str | None) -> list[dict]:
    if domain:
        results = await search(f'site:{domain} contact OR email OR "reach us"', num=6)
        if results:
            return [r.to_dict() for r in results]
    results = await search(f'"{company_name}" contact email', num=6)
    return [r.to_dict() for r in results]
