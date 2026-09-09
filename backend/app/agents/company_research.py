"""CompanyResearch + EmailDiscovery agents.

CompanyResearch: given company name + location + any search snippets about
the company, infer official website/domain/industry/description — using
ONLY facts present in the supplied search context. Confidence reflects how
certain the match is (avoid conflating two different companies with a
similar name).

EmailDiscovery: given publicly visible page snippets (e.g. a company's
"Contact Us" page indexed by search), extract a genuine public business
email if one is visible. NEVER invent or guess an email address (System.txt
section 11: "Do NOT guess emails. Do NOT invent contact names.").
"""
from app.integrations.openai_client import structured_completion
from app.integrations.web_search import search

COMPANY_SCHEMA = {
    "type": "object",
    "properties": {
        "official_website": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
        "industry": {"type": ["string", "null"]},
        "company_description": {"type": ["string", "null"]},
        "linkedin_url": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
        "website_confidence": {"type": "number"},
    },
    "required": ["official_website", "domain", "industry", "company_description",
                 "linkedin_url", "phone", "website_confidence"],
    "additionalProperties": False,
}

COMPANY_SYSTEM_PROMPT = """You research a company using ONLY the provided search result
snippets (title, link, snippet for several web search hits about the
company). Identify which result (if any) is the company's own official
website versus a directory/aggregator/unrelated company with a similar
name. Do not fabricate a website, domain, phone number or description that
isn't supported by the snippets. If uncertain, set the field to null and
lower website_confidence. website_confidence is 0-1."""

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "email": {"type": ["string", "null"]},
        "email_type": {"type": "string", "enum": ["GENERIC", "HR", "FOUNDER", "DEPARTMENT", "UNKNOWN"]},
        "email_source_url": {"type": ["string", "null"]},
        "email_confidence": {"type": "number"},
        "contact_name": {"type": ["string", "null"]},
        "designation": {"type": ["string", "null"]},
    },
    "required": ["email", "email_type", "email_source_url", "email_confidence", "contact_name", "designation"],
    "additionalProperties": False,
}

EMAIL_SYSTEM_PROMPT = """You extract a genuinely publicly-visible business email address for a
company from the provided search snippets only (e.g. text from a Contact Us
page, About page, or footer that a search engine has indexed). Rules:
- NEVER invent or guess an email address (e.g. never construct
  info@<domain> unless that literal string appears in the source text).
- NEVER return a personal/private email not clearly published as a business
  contact.
- If no email is visible in the provided text, return email=null and
  email_confidence=0.
- contact_name/designation should be null unless a named person is
  explicitly associated with that email in the source text — never invent a
  plausible-sounding name."""


def research_company(company_name: str, city: str | None, state: str | None,
                      search_snippets: list[dict]) -> dict | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nLocation: {city or ''}, {state or ''}\n\n"
        f"Search results:\n{context}\n\nIdentify the official website and company details."
    )
    return structured_completion(
        system_prompt=COMPANY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=COMPANY_SCHEMA,
        schema_name="company_research",
    )


def discover_email(company_name: str, domain: str | None, search_snippets: list[dict]) -> dict | None:
    context = "\n".join(
        f"- Title: {s['title']}\n  URL: {s['link']}\n  Snippet: {s['snippet']}" for s in search_snippets
    ) or "(no search results found)"
    user_prompt = (
        f"Company name: {company_name}\nDomain: {domain or 'unknown'}\n\n"
        f"Search results (contact/about pages):\n{context}\n\nExtract a public business email if present."
    )
    return structured_completion(
        system_prompt=EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=EMAIL_SCHEMA,
        schema_name="email_discovery",
    )


async def gather_company_snippets(company_name: str, city: str | None, state: str | None) -> list[dict]:
    location = " ".join(t for t in [city, state] if t)
    results = await search(f'"{company_name}" {location} official website', num=6)
    return [r.to_dict() for r in results]


async def gather_contact_snippets(company_name: str, domain: str | None) -> list[dict]:
    if domain:
        results = await search(f'site:{domain} contact OR email OR "reach us"', num=6)
        if results:
            return [r.to_dict() for r in results]
    results = await search(f'"{company_name}" contact email', num=6)
    return [r.to_dict() for r in results]
