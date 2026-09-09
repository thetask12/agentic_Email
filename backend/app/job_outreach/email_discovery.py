"""
Company research + official-email discovery for the Job Outreach module.
Structured outputs are Pydantic BaseModel classes (see ai_client.py's
client.beta.chat.completions.parse()) rather than raw JSON-schema dicts —
type-checked, auto-validated results instead of a plain dict the caller has
to trust field-by-field.

PRIMARY discovery path is fetch_emails_from_website(): once research_company()
has confidently identified a company's actual official website, this reads
that site's own pages directly (homepage, /contact, /about, /careers — a
plain public GET, never a login/scrape of gated content) and extracts any
visible email addresses with a regex. This is far more reliable than
guessing an email from generic search-result snippets (the previous sole
approach), which was occasionally matching an email from a completely
unrelated page (e.g. a YouTube video that happened to mention the company's
name) to the wrong company. discover_email() (the snippet-based AI
classifier) is kept as a fallback for when the website fetch finds no email
at all.

Same official-email-only filter rule as the main system: only email_type
GENERIC or FOUNDER are ever accepted as an outreach recipient — see
app.job_outreach.models.ACCEPTED_EMAIL_TYPES and service.py, which is where
the actual accept/reject decision is enforced (this module only classifies).
"""
from __future__ import annotations

import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel

from app.job_outreach.ai_client import structured_completion
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


class CompanyResearch(BaseModel):
    official_website: str | None
    domain: str | None
    website_confidence: float


class EmailDiscovery(BaseModel):
    email: str | None
    email_type: Literal["GENERIC", "HR", "FOUNDER", "DEPARTMENT", "UNKNOWN"]
    email_source_url: str | None
    email_confidence: float


COMPANY_SYSTEM_PROMPT = """You research a company using ONLY the provided search result
snippets (title, link, snippet for several web search hits about the
company). Identify which result (if any) is the company's own official
website versus a directory/aggregator/unrelated company with a similar
name. Do not fabricate a website or domain that isn't supported by the
snippets. If uncertain, set the field to null and lower
website_confidence. website_confidence is 0-1."""

EMAIL_SYSTEM_PROMPT = """You extract a genuinely publicly-visible official business email address
for a company from the provided text only (either search snippets, or real
email addresses actually found on the company's own website).
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


def research_company(company_name: str, city: str | None, search_snippets: list[dict]) -> CompanyResearch | None:
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
        response_model=CompanyResearch,
    )


def discover_email(company_name: str, domain: str | None, search_snippets: list[dict]) -> EmailDiscovery | None:
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
        response_model=EmailDiscovery,
    )


class WebsiteFetchResult(BaseModel):
    """Not an AI output — a plain container for fetch_emails_from_website()'s
    two kinds of findings: emails a regex could confidently extract, and the
    raw page text itself (for a page where a regex found nothing, e.g. a
    large corporate site that only exposes a contact form, an obfuscated
    address like "info [at] company [dot] com", or an email embedded in a
    way the regex doesn't match). Keeping both lets classify_emails() fall
    back to reading the actual page text with an AI model instead of giving
    up the moment the regex comes back empty."""
    model_config = {"arbitrary_types_allowed": True}
    emails: list[str]
    page_texts: dict[str, str]


async def fetch_emails_from_website(domain: str) -> WebsiteFetchResult:
    """Fetches the company's own homepage plus a few common pages
    (/contact, /about, /careers), extracts any visible email addresses via
    regex, and also keeps the raw page text for each successfully-fetched
    page (used as a fallback input to classify_emails() when the regex finds
    nothing — many larger corporate sites only expose a contact form or an
    obfuscated address that a plain regex won't catch, but an AI reading the
    actual page text often still can). Plain public GET requests only — no
    login, no scraping behind auth/CAPTCHA, same rule as everywhere else in
    this system. Never raises; a single company's site being unreachable
    just means empty results, not a crashed search cycle."""
    if not domain:
        return WebsiteFetchResult(emails=[], page_texts={})
    found: list[str] = []
    seen: set[str] = set()
    page_texts: dict[str, str] = {}
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
                page_texts[url] = resp.text[:6000]
                for match in _EMAIL_RE.findall(resp.text):
                    if _is_junk_email(match) or match.lower() in seen:
                        continue
                    seen.add(match.lower())
                    found.append(match)
                break  # https worked (or returned a real response) — skip http fallback for this path
            if len(found) >= 5:
                break  # enough candidates gathered — no need to keep crawling more pages
    logger.info("JOB_OUTREACH_WEBSITE_FETCH domain=%r emails_found=%d pages_fetched=%d",
                domain, len(found), len(page_texts))
    return WebsiteFetchResult(emails=found, page_texts=page_texts)


def classify_emails(company_name: str, domain: str | None, fetch_result: WebsiteFetchResult) -> EmailDiscovery | None:
    """AI-classifies the results of fetch_emails_from_website() into a
    single EmailDiscovery — the best email to use as the outreach recipient.

    If the regex found candidate emails, those are listed as the primary
    input (every candidate is a real address that was actually present on
    the company's own site, not inferred from a search snippet — far more
    reliable than discover_email()).

    If the regex found nothing at all but pages were still fetched, the raw
    page text itself is given to the model instead — many larger corporate
    sites only expose a contact form or an obfuscated address ("info [at]
    company [dot] com") that a plain regex won't catch, but a model reading
    the actual page text can often still recognize. Returns None only if no
    pages were fetched at all (site unreachable/no domain)."""
    if not fetch_result.page_texts:
        return None
    if fetch_result.emails:
        listing = "\n".join(f"- {e}" for e in fetch_result.emails)
        source_block = f"Email addresses found on this company's own website:\n{listing}"
    else:
        pages = "\n\n".join(f"--- {url} ---\n{text}" for url, text in fetch_result.page_texts.items())
        source_block = (
            "No email address was found by a plain pattern match, but here is the raw "
            f"text of this company's own contact/about/careers pages — look carefully for "
            f"an email that may be obfuscated or written unusually (e.g. 'name [at] domain "
            f"[dot] com'):\n\n{pages}"
        )
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"{source_block}\n\nPick the single best email to use as an outreach contact and classify it. "
        f"If genuinely no email is present anywhere in this text, return email=null, "
        f"email_type=\"UNKNOWN\", email_confidence=0."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=EmailDiscovery,
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
