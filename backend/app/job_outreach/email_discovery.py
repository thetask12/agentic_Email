"""
Company research + official-email discovery for the Job Outreach module —
same two-agent pattern as app/agents/company_research.py (research_company +
discover_email), reusing the shared app.integrations.openai_client
structured_completion() and app.integrations.web_search.search() helpers
(both generic, provider-level integrations safe to share across modules).

Same official-email-only filter rule as the main system: only email_type
GENERIC or FOUNDER are ever accepted as an outreach recipient — see
app.job_outreach.models.ACCEPTED_EMAIL_TYPES and service.py, which is where
the actual accept/reject decision is enforced (this module only classifies).
"""
from __future__ import annotations

from app.integrations.openai_client import structured_completion
from app.integrations.web_search import search

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
